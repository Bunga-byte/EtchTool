import {
  Activity,
  Clock3,
  FileSearch,
  FlaskConical,
  ShieldCheck,
} from "lucide-react";
import { useApi } from "../api";
import { formatNumber as num } from "../utils";

import {
  Badge,
  BarChart,
  LineChart,
  Metric,
  Notice,
  Panel,
  State,
} from "../components";
export function Analytics() {
  const api = useApi("/api/analytics"),
    d = api.data,
    r = d?.rate || {};
  return (
    <State {...api}>
      <div className="metrics-grid three">
        <Metric
          label="Confirmed RF-cohort episodes"
          value={r.failures}
          icon={FileSearch}
          note="Eligible matching-module cohort, not total fleet"
        />
        <Metric
          label="Eligible operating exposure"
          value={r.exposure_hours}
          unit="h"
          icon={Clock3}
          note="Cohort-matched component exposure"
        />
        <Metric
          label="Failure rate / 1,000 h"
          value={r.rate_per_1000_hours}
          icon={Activity}
          note={`95% CI: ${num(r.lower, 3)} – ${num(r.upper, 3)} per 1,000 h`}
          tone="blue"
        />
      </div>
      <Notice>
        Analysis uses synthetic records only. Confidence intervals describe
        sampling uncertainty; they do not correct missing records or establish
        causality.
      </Notice>
      <div className="cohort-context">
        <strong>Analysis population</strong>
        <p>{d?.cohort || "Cohort definition not supplied."}</p>
        <span>
          {num(d?.eligible_rate_components, 0)} eligible rate components ·{" "}
          {num(d?.observations?.length, 0)} eligible first-life observations.
          Incomplete or disputed records are excluded with their corresponding
          failures.
        </span>
        {!!d?.excluded_components?.length && (
          <details>
            <summary>
              Inspect excluded components ({d.excluded_components.length}{" "}
              analysis exclusions)
            </summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Analysis</th>
                    <th>Exclusion reason</th>
                  </tr>
                </thead>
                <tbody>
                  {d.excluded_components.map((item: any, i: number) => (
                    <tr key={i}>
                      <td className="mono">{item.component_id}</td>
                      <td>{item.analysis}</td>
                      <td className="exclusion-reason">{item.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </div>
      <div className="two-column">
        <Panel
          title="Kaplan–Meier survival"
          description="Right-censored observations retained · component operating exposure"
        >
          <LineChart
            points={d?.survival || []}
            percent
            labelText="Kaplan–Meier survival probability by exposure hours"
          />
          <div className="panel-footnote">
            Removal without a confirmed failure is treated as censoring. Mixed
            conditions require stratification before use.
          </div>
        </Panel>
        <Panel
          title="Revision comparison"
          description="Compare denominators as well as observed failure counts"
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Revision</th>
                  <th>Failures</th>
                  <th>Exposure h</th>
                  <th>Rate / 1,000 h</th>
                </tr>
              </thead>
              <tbody>
                {(d?.revision_comparison || []).map((row: any, i: number) => (
                  <tr key={i}>
                    <td className="mono">{row.revision}</td>
                    <td>{num(row.failures, 0)}</td>
                    <td>{num(row.exposure_hours)}</td>
                    <td>{num(row.rate_per_1000_hours, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel-footnote">
            Different conditions, lots, refurbishment, and commissioning phases
            can confound revision comparisons.
          </div>
        </Panel>
      </div>
      <div className="two-column">
        <Panel
          title="Attributed downtime"
          description="Overlapping intervals are unioned before fleet aggregation"
        >
          <BarChart items={d?.downtime_by_subsystem || []} />
        </Panel>
        <Panel
          title="Model eligibility & assumptions"
          description="Evidence gates precede predictive claims"
        >
          <div className="model-status">
            <FlaskConical size={23} />
            <div>
              <h3>Weibull analysis</h3>
              <Badge
                value={
                  d?.weibull?.eligible ? "eligible" : "insufficient evidence"
                }
              />
              <p>
                {d?.weibull?.message ||
                  d?.weibull?.reason ||
                  "A sufficiently sized, appropriate lifetime cohort is required before fitting."}
              </p>
              {d?.weibull?.shape != null && (
                <p>
                  Shape: {num(d.weibull.shape, 3)} · Scale:{" "}
                  {num(d.weibull.scale)} h
                </p>
              )}
            </div>
          </div>
          <div className="model-status">
            <ShieldCheck size={23} />
            <div>
              <h3>Prediction governance</h3>
              <p>
                {d?.forecast_policy?.message ||
                  "No production-validated health model is available. Synthetic demonstrations support architecture validation only."}
              </p>
              <p>
                Tool/campaign holdouts · temporal leakage checks · censoring
                awareness · model version traceability.
              </p>
            </div>
          </div>
        </Panel>
      </div>
      <TeachingForecast />
    </State>
  );
}

function TeachingForecast() {
  const api = useApi("/api/forecast/demo"),
    model = api.data;
  return (
    <Panel
      title="Statistical teaching model · separate synthetic cohort"
      description="Architecture demonstration only · not a prediction for the displayed fleet or its components"
    >
      <State {...api}>
        <div className="teaching-model-header">
          <FlaskConical size={22} />
          <div>
            <strong>
              {model?.label || "Synthetic statistical demonstration"}
            </strong>
            <p>{model?.dataset}</p>
            <small className="mono">
              Model version: {model?.model_version || "Unavailable"}
            </small>
          </div>
          <Badge value="synthetic only" />
        </div>
        <Notice kind="warning">
          These probabilities come from a separate, fictional teaching cohort.
          They are not estimates for any displayed installed component, and have
          no production validation, calibration, false-alert, or
          warning-lead-time evidence.
        </Notice>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Future exposure horizon</th>
                <th>Illustrative failure probability</th>
                <th>95% confidence interval</th>
                <th>Model state</th>
              </tr>
            </thead>
            <tbody>
              {(model?.horizons || []).map((h: any, i: number) => (
                <tr key={i}>
                  <td>
                    Next {num(h.horizon, 0)} {h.unit}
                  </td>
                  <td>{num(h.probability * 100, 2)}%</td>
                  <td>
                    {num(h.lower * 100, 2)}% – {num(h.upper * 100, 2)}%
                  </td>
                  <td>State B · statistical estimate</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel-footnote">
          {num(model?.evidence?.observations, 0)} teaching observations ·{" "}
          {num(model?.evidence?.failures, 0)} fictional failures ·{" "}
          {num(model?.evidence?.right_censored, 0)} right-censored lifetimes.
          Constant-rate assumption; interval covers rate sampling uncertainty
          only.
          <details>
            <summary>Model limitations and risk factors</summary>
            <ul>
              {(model?.limitations || []).map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        </div>
      </State>
    </Panel>
  );
}
