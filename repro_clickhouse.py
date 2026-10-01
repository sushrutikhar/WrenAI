"""Run each dialect-neutral query through WrenEngine against a real ClickHouse and print
what comes back - the result rows, or the actual error. Used to produce the evidence
for the pull request, once on upstream main and once on the fix branch."""

from __future__ import annotations

import base64
import json
import os
import sys

from wren import DataSource, WrenEngine

MANIFEST = {
    "catalog": "wren",
    "schema": "public",
    "models": [
        {
            "name": "orders",
            "tableReference": {"schema": "repro", "table": "orders"},
            "columns": [
                {"name": "o_orderkey", "type": "integer"},
                {"name": "o_custkey", "type": "integer"},
                {"name": "o_totalprice", "type": "double"},
                {"name": "o_orderdate", "type": "date"},
            ],
            "primaryKey": "o_orderkey",
        },
        {
            "name": "customer",
            "tableReference": {"schema": "repro", "table": "customer"},
            "columns": [
                {"name": "c_custkey", "type": "integer"},
                {"name": "c_name", "type": "varchar"},
            ],
            "primaryKey": "c_custkey",
        },
    ],
}

QUERIES = {
    "lag": "SELECT o_orderkey, LAG(o_totalprice) OVER (ORDER BY o_orderkey) AS prev "
    "FROM orders ORDER BY o_orderkey",
    "lead": "SELECT o_orderkey, LEAD(o_totalprice, 1) OVER (ORDER BY o_orderkey) AS nxt "
    "FROM orders ORDER BY o_orderkey",
    "cume_dist": "SELECT o_orderkey, CUME_DIST() OVER (ORDER BY o_custkey) AS cd "
    "FROM orders ORDER BY o_orderkey",
    "extract_dow": "SELECT o_orderkey, EXTRACT(DOW FROM o_orderdate) AS dow "
    "FROM orders ORDER BY o_orderkey",
    "null_cast": "SELECT o_orderkey, CAST(NULL AS DOUBLE) AS x FROM orders "
    "ORDER BY o_orderkey",
    "exists": "SELECT c.c_name FROM customer AS c WHERE EXISTS (SELECT 1 FROM orders AS o "
    "WHERE o.o_custkey = c.c_custkey) ORDER BY c.c_name",
    "not_exists": "SELECT c.c_name FROM customer AS c WHERE NOT EXISTS (SELECT 1 FROM "
    "orders AS o WHERE o.o_custkey = c.c_custkey) ORDER BY c.c_name",
    "cume_dist_named": "SELECT o_orderkey, CUME_DIST() OVER w AS cd FROM orders "
    "WINDOW w AS (PARTITION BY o_custkey ORDER BY o_totalprice) ORDER BY o_orderkey",
    "lag_named": "SELECT o_orderkey, LAG(o_totalprice) OVER w AS prev FROM orders "
    "WINDOW w AS (PARTITION BY o_custkey ORDER BY o_orderkey) ORDER BY o_orderkey",
    "exists_count": "SELECT c.c_name FROM customer AS c WHERE EXISTS (SELECT COUNT(*) "
    "FROM orders AS o WHERE o.o_custkey = c.c_custkey) ORDER BY c.c_name",
    "having_alias": "SELECT o_custkey, SUM(o_totalprice) AS o_totalprice FROM orders "
    "GROUP BY o_custkey HAVING SUM(o_totalprice) > 15 ORDER BY o_custkey",
}


def main() -> int:
    info = {
        "host": os.environ.get("CH_HOST", "localhost"),
        "port": os.environ.get("CH_PORT", "8123"),
        "database": "repro",
        "user": os.environ.get("CH_USER", "default"),
        "password": os.environ.get("CH_PASSWORD", ""),
    }
    manifest = base64.b64encode(json.dumps(MANIFEST).encode()).decode()
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    with WrenEngine(manifest, DataSource.clickhouse, info) as engine:
        for name, sql in QUERIES.items():
            print(f"### {label} :: {name}")
            try:
                planned = engine.dry_plan(sql)
                outer = planned[planned.rfind(") SELECT ") + 2 :]
                print(f"planned: {outer}")
                rows = engine.query(sql).to_pylist()
                print(f"result:  {rows}")
            except Exception as exc:  # noqa: BLE001 - the error IS the evidence
                print(f"error:   {type(exc).__name__}: {str(exc).splitlines()[0][:400]}")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
