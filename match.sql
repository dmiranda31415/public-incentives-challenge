-- usa mais probes se precisares de melhor recall (ajusta k)
SET ivfflat.probes = 10;

TRUNCATE TABLE matches;

WITH topk AS (
  SELECT
    i.incentive_pk AS iid,
    i.embedding    AS iemb,
    COALESCE(i.eligibility, '{}'::jsonb) AS eligibility,
    c.id           AS cid,
    c.embedding    AS cemb,
    c.company_name,
    c.cae_primary_label,
    c.trade_description_native,
    lower(
      COALESCE(c.trade_description_native, '') || ' ' ||
      COALESCE(c.company_name, '')
    ) AS company_text
  FROM incentives i
  JOIN LATERAL (
    SELECT id, embedding, company_name, cae_primary_label, trade_description_native
    FROM companies
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> i.embedding
    LIMIT 200
  ) c ON TRUE
  WHERE i.embedding IS NOT NULL
),
rules AS (
  SELECT
    t.iid,
    t.cid,
    t.cae_primary_label,
    t.trade_description_native,
    t.company_text,
    t.eligibility,
    CASE
      WHEN jsonb_array_length(COALESCE(t.eligibility->'allowed_cae_labels', '[]'::jsonb)) = 0
        THEN TRUE
      ELSE EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(t.eligibility->'allowed_cae_labels') lab
        WHERE lab ILIKE t.cae_primary_label
      )
    END AS passes_cae,
    CASE
      WHEN jsonb_array_length(COALESCE(t.eligibility->'keywords_required', '[]'::jsonb)) = 0
        THEN TRUE
      ELSE NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(t.eligibility->'keywords_required') kw
        WHERE t.company_text NOT ILIKE '%'||kw||'%'
      )
    END AS passes_kw_required,
    COALESCE((
      SELECT COUNT(*)
      FROM jsonb_array_elements_text(COALESCE(t.eligibility->'keywords_bonus', '[]'::jsonb)) kwb
      WHERE t.company_text ILIKE '%'||kwb||'%'
    ), 0) AS bonus_hits
  FROM topk t
),
scored AS (
  SELECT
    r.iid,
    r.cid,
    1 - (t.iemb <=> t.cemb) AS sim,
    (r.passes_cae AND r.passes_kw_required) AS rule_pass,
    r.bonus_hits
  FROM rules r
  JOIN topk t ON t.iid = r.iid AND t.cid = r.cid
),
ranked AS (
  SELECT
    s.iid AS incentive_id,
    s.cid AS company_id,
    (
      0.70 * s.sim +
      0.25 * CASE WHEN s.rule_pass THEN 1 ELSE -1 END +
      0.05 * LEAST(s.bonus_hits, 3)
    ) AS score,
    s.rule_pass,
    ROW_NUMBER() OVER (
      PARTITION BY s.iid
      ORDER BY s.rule_pass DESC,
               (
                 0.70 * s.sim +
                 0.25 * CASE WHEN s.rule_pass THEN 1 ELSE -1 END +
                 0.05 * LEAST(s.bonus_hits, 3)
               ) DESC
    ) AS rnk
  FROM scored s
)
INSERT INTO matches (incentive_id, company_id, score, rank, rule_pass, explanation)
SELECT
  r.incentive_id,
  r.company_id,
  r.score,
  r.rnk,
  to_jsonb(r.rule_pass),
  NULL::text
FROM ranked r
WHERE r.rnk <= 5
ON CONFLICT (incentive_id, company_id) DO UPDATE
SET score = EXCLUDED.score,
    rank  = EXCLUDED.rank,
    rule_pass = EXCLUDED.rule_pass;
