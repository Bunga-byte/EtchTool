import { expect, test } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

const headers = { Authorization: "Bearer synthetic-browser-editor" };

async function stageDocument(
  request: APIRequestContext,
  sourceId: string,
  originalId: string,
) {
  const created = await request.post("/api/enterprise/jobs", {
    headers,
    data: {
      source_id: sourceId,
      kind: "backfill",
      window_start: "2026-01-01T00:00:00Z",
      window_end: "2026-02-01T00:00:00Z",
      query: { original_ids: [originalId] },
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const job = await created.json();
  const run = await request.post(`/api/enterprise/jobs/${job.id}/run`, {
    headers,
    data: {},
  });
  expect(run.status(), await run.text()).toBe(200);
  expect((await run.json()).status).toBe("succeeded");
  const documents = await (
    await request.get(`/api/enterprise/documents?source_id=${sourceId}`)
  ).json();
  const document = documents.items.find(
    (item: any) => item.original_id === originalId,
  );
  expect(document).toBeTruthy();
  return document;
}

async function enterpriseWorkspace(page: Page) {
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: "Data integrations", exact: true })
    .click();
  await page
    .getByRole("tab", { name: "Enterprise handoff workspace", exact: true })
    .click();
  return page.getByRole("navigation", {
    name: "Enterprise integration workspace",
  });
}

async function authorize(page: Page) {
  await page
    .getByRole("button", { name: "Access settings", exact: true })
    .click();
  await page
    .getByLabel("Authorized local bearer token")
    .fill("synthetic-browser-editor");
  await page
    .getByRole("button", { name: "Use for this session", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test.describe.serial("enterprise integration handoff workflows", () => {
  test("a viewer inspects original evidence and dry-runs field mappings without saving records", async ({
    page,
    request,
  }) => {
    const document = await stageDocument(request, "informs-demo", "syn-pm-001");
    const beforeInventory = await (await request.get("/api/inventory")).json();
    const beforeProposals = await (
      await request.get("/api/enterprise/proposals")
    ).json();
    await page.goto("/");
    const nav = await enterpriseWorkspace(page);
    await expect(
      page.getByRole("heading", { name: "Registered integration sources" }),
    ).toBeVisible();
    await nav
      .getByRole("button", { name: "Ingestion jobs", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Create ingestion job", exact: true }),
    ).toBeDisabled();
    await nav
      .getByRole("button", { name: "Original documents", exact: true })
      .click();
    await page
      .getByLabel("Search original documents")
      .fill(document.original_id);
    await page
      .locator(".enterprise-record-picker button")
      .filter({ hasText: document.original_id })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Original source evidence",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator(".document-evidence")).toContainText(
      "SYN-01A-VALVE-001",
    );
    await expect(page.locator(".original-evidence mark").first()).toBeVisible();
    await page
      .getByLabel("Field mapping (JSON)", { exact: true })
      .fill('{"Component serial":"component_serial"}');
    const previewResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith("/mapping-preview") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Preview field mapping", exact: true })
      .click();
    const preview = await previewResponse;
    expect(preview.status()).toBe(200);
    const result = await preview.json();
    expect(result).toMatchObject({
      dry_run: true,
      canonical_records_changed: false,
    });
    expect(result.proposals.length).toBeGreaterThan(0);
    await expect(
      page.getByText("Read-only dry run.", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("No canonical records changed.", { exact: false }),
    ).toBeVisible();
    expect(
      (await (await request.get("/api/enterprise/proposals")).json()).items,
    ).toHaveLength(beforeProposals.items.length);
    expect(
      (await (await request.get("/api/inventory")).json()).items.map(
        (item: any) => item.serial_number,
      ),
    ).toEqual(beforeInventory.items.map((item: any) => item.serial_number));
  });

  test("diagnostic mapping approval enables scoped component traces while RF calculations remain gated", async ({
    page,
    request,
  }) => {
    await stageDocument(request, "fdc-demo", "syn-fdc-001");
    const before = await (
      await request.get("/api/components/cmp-1-a-rf")
    ).json();
    const mappingData = await (
      await request.get("/api/enterprise/mappings")
    ).json();
    const mapping = mappingData.items.find(
      (item: any) => item.relationship === "supporting_diagnostic",
    );
    expect(mapping?.verification).toBe("proposed");
    await page.goto("/");
    const nav = await enterpriseWorkspace(page);
    await nav
      .getByRole("button", { name: "Sensor registry", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Equipment sensor catalog",
        exact: true,
      }),
    ).toBeVisible();
    // Mapping IDs appear in the API; the UI identifies the physical relationship and channel.
    const diagnostic = page
      .locator(".mapping-card")
      .filter({ hasText: mapping.physical_explanation });
    await expect(
      diagnostic.getByRole("button", { name: "Approve mapping", exact: true }),
    ).toBeDisabled();
    await authorize(page);
    await diagnostic
      .getByLabel("Mapping review note", { exact: true })
      .fill(
        "Synthetic browser approval: supporting diagnostic context only, without a predictive health claim.",
      );
    const approvalResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/mappings/${mapping.id}/review`) &&
        response.request().method() === "POST",
    );
    await diagnostic
      .getByRole("button", { name: "Approve mapping", exact: true })
      .click();
    const approved = await approvalResponse;
    expect(approved.status()).toBe(200);
    expect((await approved.json()).verification).toBe("approved");
    await expect(
      diagnostic.getByText("approved", { exact: true }),
    ).toBeVisible();
    const rules = await (
      await request.get("/api/enterprise/exposure-rules")
    ).json();
    expect(
      rules.items.every((rule: any) => rule.verification === "proposed"),
    ).toBe(true);
    await page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("button", { name: "Chamber inventory", exact: true })
      .click();
    await page.getByLabel("Tool", { exact: true }).selectOption("tool-1");
    await page.getByLabel("Chamber", { exact: true }).selectOption("ch-1-a");
    await page
      .getByRole("button", { name: "Open SYN-01A-RF-002", exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    await dialog
      .getByRole("tab", { name: "Telemetry & lineage", exact: true })
      .click();
    await expect(
      dialog.getByText("Diagnostic telemetry.", { exact: true }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("img", {
        name: "Component diagnostic telemetry over observed operating time",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("heading", {
        name: "Exposure calculation lineage",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      dialog.getByText(
        "No approved imported-exposure calculation has been recorded for this component.",
        { exact: false },
      ),
    ).toBeVisible();
    await dialog
      .getByLabel("Operating-state filter", { exact: true })
      .fill("nonexistent-synthetic-state");
    await dialog
      .getByRole("button", { name: "Apply telemetry window", exact: true })
      .click();
    await expect(
      dialog.getByText("No numeric measurements are available for a plot.", {
        exact: false,
      }),
    ).toBeVisible();
    expect(
      (
        await (
          await request.get("/api/enterprise/components/cmp-1-a-rf/lineage")
        ).json()
      ).items,
    ).toHaveLength(0);
    const after = await (
      await request.get("/api/components/cmp-1-a-rf")
    ).json();
    expect(after.exposure.hours).toBe(before.exposure.hours);
    expect(after.pm.status).toBe(before.pm.status);
  });
  test("approved source replacement and RF rules propagate through component PM and calculation lineage", async ({
    page,
    request,
  }) => {
    const before = await (
      await request.get("/api/inventory?chamber_id=ch-1-a")
    ).json();
    expect(
      before.items.some((item: any) => item.serial_number === "SYN-01A-RF-002"),
    ).toBe(true);
    await page.goto("/");
    await authorize(page);
    const nav = await enterpriseWorkspace(page);
    await nav
      .getByRole("button", { name: "Ingestion jobs", exact: true })
      .click();
    await page
      .getByLabel("Ingestion source", { exact: true })
      .selectOption("informs-demo");
    await page
      .getByLabel("Scoped query (JSON)", { exact: true })
      .fill('{"original_ids":["syn-replacement-001"]}');
    const createResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/enterprise/jobs") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Create ingestion job", exact: true })
      .click();
    const created = await createResponse;
    expect(created.status()).toBe(201);
    const job = await created.json();
    const card = page.locator(".enterprise-job").filter({ hasText: job.id });
    const runResponse = page.waitForResponse((response) =>
      response.url().endsWith(`/jobs/${job.id}/run`),
    );
    await card
      .getByRole("button", { name: "Run processing pass", exact: true })
      .click();
    expect((await runResponse).status()).toBe(200);
    await expect(card).toContainText("succeeded");
    await card
      .getByText("Checkpoint, operational metrics, and errors", { exact: true })
      .click();
    await expect(card.locator("pre")).toContainText('"complete": true');
    await nav
      .getByRole("button", { name: "Original documents", exact: true })
      .click();
    await page
      .getByLabel("Search original documents")
      .fill("syn-replacement-001");
    await page
      .locator(".enterprise-record-picker button")
      .filter({ hasText: "syn-replacement-001" })
      .click();
    const original = page.locator(".document-evidence");
    await expect(original).toContainText("SYN-01A-RF-002");
    await expect(original).toContainText("SYN-01A-RF-003");
    await page
      .locator(".enterprise-proposal-link")
      .filter({ hasText: "replacement" })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Proposed canonical change",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "Original evidence beside extracted claims",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page
        .locator(".original-evidence mark")
        .filter({ hasText: "SYN-01A-RF-003" }),
    ).toBeVisible();
    await page
      .getByLabel("Engineering review decision", { exact: true })
      .selectOption("approve");
    await page
      .getByLabel("Engineering review note", { exact: true })
      .fill(
        "Synthetic browser review: source spans establish the planned old-to-new serialized replacement; no hardware failure is inferred.",
      );
    const reviewResponse = page.waitForResponse(
      (response) =>
        /\/proposals\/[^/]+\/review$/.test(response.url()) &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Submit engineering review", exact: true })
      .click();
    const reviewed = await reviewResponse;
    expect(reviewed.status()).toBe(200);
    const outcome = await reviewed.json();
    expect(outcome.proposal.status).toBe("approved");
    expect(outcome.canonical.failure_created).toBe(false);
    await expect(
      page.getByText("approve · browser-test", { exact: true }),
    ).toBeVisible();

    // The preceding test imported telemetry and approved the diagnostic mapping.
    // A distinct operating-exposure mapping and rule still require human review.
    const mappings = await (
      await request.get("/api/enterprise/mappings")
    ).json();
    const exposureMapping = mappings.items.find(
      (mapping: any) => mapping.relationship === "exposure_counter",
    );
    expect(exposureMapping.verification).toBe("proposed");
    await nav
      .getByRole("button", { name: "Sensor registry", exact: true })
      .click();
    const mappingCard = page
      .locator(".mapping-card")
      .filter({ hasText: exposureMapping.physical_explanation });
    await mappingCard
      .getByLabel("Mapping review note", { exact: true })
      .fill(
        "Synthetic approval: this source-specific on/off channel measures primary RF exposure for the configured component.",
      );
    const mappingResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/mappings/${exposureMapping.id}/review`) &&
        response.request().method() === "POST",
    );
    await mappingCard
      .getByRole("button", { name: "Approve mapping", exact: true })
      .click();
    expect((await mappingResponse).status()).toBe(200);
    const rules = await (
      await request.get("/api/enterprise/exposure-rules")
    ).json();
    expect(rules.items).toHaveLength(1);
    const rule = rules.items[0];
    expect(rule.verification).toBe("proposed");
    const ruleCard = page.locator(".mapping-card").filter({ hasText: rule.id });
    await ruleCard
      .getByLabel("Exposure rule review note", { exact: true })
      .fill(
        "Synthetic approval: explicit on/off states, union aggregation, bounded gaps, revision and effective dates are documented.",
      );
    const ruleResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/exposure-rules/${rule.id}/review`) &&
        response.request().method() === "POST",
    );
    await ruleCard
      .getByRole("button", { name: "Approve exposure rule", exact: true })
      .click();
    expect((await ruleResponse).status()).toBe(200);

    const componentResponse = await request.get(
      "/api/components/cmp-enterprise-spare",
    );
    expect(componentResponse.status()).toBe(200);
    const component = await componentResponse.json();
    expect(component.serial_number).toBe("SYN-01A-RF-003");
    expect(component.exposure.hours).toBeCloseTo(60, 8);
    expect(component.pm.threshold).toBe(650);
    expect(component.pm.remaining).toBeCloseTo(590, 8);
    expect(component.pm.percent_consumed).toBe(9.23);
    const removed = await (
      await request.get("/api/components/cmp-1-a-rf")
    ).json();
    expect(removed.removed_at).toContain("2026-01-26T00:00:00");
    expect(removed.exposure.hours).toBeCloseTo(70, 8);

    await page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("button", { name: "Chamber inventory", exact: true })
      .click();
    await page.getByLabel("Tool", { exact: true }).selectOption("tool-1");
    await page.getByLabel("Chamber", { exact: true }).selectOption("ch-1-a");
    await expect(
      page.getByRole("button", { name: "Open SYN-01A-RF-002", exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Open SYN-01A-RF-003", exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    const exposureMetric = dialog
      .locator(".metric")
      .filter({ hasText: "Since installation" });
    await expect(exposureMetric.locator(".metric-value")).toHaveText(
      /^\s*60\s*RF h\s*$/,
    );
    const remainingMetric = dialog
      .locator(".metric")
      .filter({ hasText: "PM interval remaining" });
    await expect(remainingMetric.locator(".metric-value")).toHaveText(
      /^\s*590\s*RF h\s*$/,
    );
    await expect(dialog.locator(".policy-detail")).toContainText("9% consumed");
    await dialog
      .getByRole("tab", { name: "Lifecycle history", exact: true })
      .click();
    await expect(dialog.locator(".replacement-list")).toContainText(
      "SYN-01A-RF-002",
    );
    await expect(dialog.locator(".replacement-list")).toContainText(
      "SYN-01A-RF-003",
    );
    await dialog
      .getByRole("tab", { name: "Telemetry & lineage", exact: true })
      .click();
    await expect(
      dialog.getByText("Diagnostic telemetry.", { exact: true }),
    ).toBeVisible();
    const lineageResponse = await request.get(
      "/api/enterprise/components/cmp-enterprise-spare/lineage",
    );
    expect(lineageResponse.status()).toBe(200);
    const lineage = await lineageResponse.json();
    expect(lineage.items.length).toBeGreaterThan(0);
    await expect(dialog.locator(".lineage-card")).toHaveCount(
      lineage.items.length,
    );
    await expect(dialog.locator(".lineage-card").first()).toContainText(
      lineage.items[0].method_version,
    );
    await expect(dialog.locator(".lineage-card").first()).toContainText(
      lineage.items[0].source_version_ids[0],
    );
    await dialog
      .locator(".lineage-card")
      .first()
      .getByText(
        "Inspect exact input fingerprint, derived intervals, result, and issues",
        { exact: true },
      )
      .click();
    await expect(
      dialog.locator(".lineage-card").first().locator("pre"),
    ).toContainText(lineage.items[0].input_hash);
  });
});
