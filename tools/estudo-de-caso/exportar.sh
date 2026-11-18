#!/usr/bin/env bash
# Exporta do banco os dados do estudo de caso para CSV (horários em UTC).
#
# Uso (no servidor):
#   ./exportar.sh 2026-11-05 2026-11-18 [pasta_de_saida]
# A data final é exclusiva (2026-11-18 inclui todo o dia 17).
# Variáveis opcionais: PG_CONTAINER (ufsm-timescaledb), PG_USER (ufsm), PG_DB (monitor).
set -euo pipefail

INI=${1:?informe a data inicial (AAAA-MM-DD)}
FIM=${2:?informe a data final (AAAA-MM-DD, exclusiva)}
OUT=${3:-dados}
for d in "$INI" "$FIM"; do
  [[ "$d" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "data inválida: $d" >&2; exit 1; }
done
PG_CONTAINER=${PG_CONTAINER:-ufsm-timescaledb}
PG_USER=${PG_USER:-ufsm}
PG_DB=${PG_DB:-monitor}
mkdir -p "$OUT"

JANELA="observed_at >= '$INI' AND observed_at < '$FIM'"

exporta() {  # nome, consulta
  docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -q \
    -c "COPY ($2) TO STDOUT WITH CSV HEADER" > "$OUT/$1.csv"
  echo "$1.csv: $(($(wc -l < "$OUT/$1.csv") - 1)) linhas"
}

exporta icmp "SELECT observed_at, probe_id, target, packets_sent, packets_received, loss_pct,
  rtt_min_ms, rtt_avg_ms, rtt_max_ms, jitter_ms, rtt_p95_ms FROM icmp_measurements WHERE $JANELA ORDER BY observed_at"

exporta http "SELECT observed_at, probe_id, target, http_status, dns_ms, tcp_connect_ms, tls_handshake_ms,
  ttfb_ms, total_ms, response_bytes FROM http_measurements WHERE $JANELA ORDER BY observed_at"

exporta iperf "SELECT observed_at, probe_id, target, target_probe, direction, duration_seconds,
  bytes_transferred, throughput_bps, retransmits FROM iperf_measurements WHERE $JANELA ORDER BY observed_at"

exporta dns "SELECT observed_at, probe_id, target, resolver, qtype, rcode, answer_count, elapsed_ms
  FROM dns_measurements WHERE $JANELA ORDER BY observed_at"

exporta traceroute "SELECT observed_at, probe_id, target, hop_count, hops FROM traceroute_measurements
  WHERE $JANELA ORDER BY observed_at"

exporta execucoes "SELECT observed_at, probe_id, measurement_type, target, target_probe, plan_id, job_id,
  status, error_message FROM measurement_runs WHERE $JANELA AND measurement_type <> 'sysinfo' ORDER BY observed_at"

exporta saude "SELECT observed_at, probe_id,
  (raw_payload->'result'->>'cpu_temp_c')::float AS cpu_temp_c,
  (raw_payload->'result'->>'cpu_usage_pct')::float AS cpu_usage_pct,
  (raw_payload->'result'->>'agent_cpu_pct')::float AS agent_cpu_pct,
  (raw_payload->'result'->>'agent_rss_kb')::float AS agent_rss_kb,
  (raw_payload->'result'->>'mem_total_kb')::float AS mem_total_kb,
  (raw_payload->'result'->>'mem_available_kb')::float AS mem_available_kb,
  (raw_payload->'result'->>'link_speed_mbps')::float AS link_speed_mbps,
  jsonb_array_length(COALESCE(raw_payload->'result'->'throttled_now', '[]'::jsonb)) AS throttled_now,
  raw_payload->'result'->>'ip_address' AS ip_address
  FROM measurement_runs WHERE $JANELA AND measurement_type = 'sysinfo' AND status = 'success' ORDER BY observed_at"

exporta destinos "SELECT name, kind, address FROM targets ORDER BY name"
exporta sondas "SELECT probe_id, address, deployment FROM probes ORDER BY probe_id"

echo "dados exportados em $OUT/ (compacte com: tar czf dados.tgz $OUT)"
