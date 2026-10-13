-- Each query is separated by a line that starts with "-- name:". report.py runs them in order.
-- Tables: scores (lead_scores.csv), sla (sla_audit.csv), qual (qualification_check.csv)

-- name: Does the tier predict a booked meeting? (net-new leads an SDR worked)
SELECT s.tier,
       COUNT(DISTINCT s.lead_id)                                   AS leads,
       COUNT(DISTINCT q.lead_id)                                   AS meetings_booked,
       ROUND(100.0 * COUNT(DISTINCT q.lead_id) / COUNT(DISTINCT s.lead_id), 1) AS booked_pct,
       COUNT(DISTINCT CASE WHEN q.sql_ts IS NOT NULL AND q.discovery_held_ts IS NOT NULL THEN q.lead_id END) AS sqls
FROM scores s
JOIN (SELECT DISTINCT lead_id FROM sla) w ON w.lead_id = s.lead_id
LEFT JOIN qual q ON q.lead_id = s.lead_id
GROUP BY s.tier
ORDER BY CASE s.tier WHEN 'Hot' THEN 1 WHEN 'Warm' THEN 2 ELSE 3 END;

-- name: SLA met, by tier and attempt (attempt 1 is the first SDR, 2 and 3 are reroutes)
SELECT tier, step AS attempt,
       COUNT(*)                                  AS assignments,
       SUM(met)                                  AS met,
       ROUND(100.0 * SUM(met) / COUNT(*), 1)     AS met_pct
FROM sla
GROUP BY tier, step
ORDER BY CASE tier WHEN 'Hot' THEN 1 WHEN 'Warm' THEN 2 ELSE 3 END, step;

-- name: SLA met, by SDR (Hot leads only)
SELECT assignee AS sdr,
       COUNT(*)                                  AS hot_assignments,
       SUM(met)                                  AS met,
       ROUND(100.0 * SUM(met) / COUNT(*), 1)     AS met_pct
FROM sla
WHERE tier = 'Hot'
GROUP BY assignee
ORDER BY met_pct;
