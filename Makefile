export OLIST_RAW_DIR ?= $(CURDIR)/data/raw
export OLIST_WAREHOUSE_PATH ?= $(CURDIR)/warehouse/olist.duckdb

.PHONY: setup build reconcile sample build-sample lint docs clean

setup:          ## install dbt, DuckDB, the analysis stack and dev tools
	pip install -e ".[analysis,dev]"

build:          ## build + test the warehouse from the real data in data/raw
	mkdir -p warehouse && cd transform && dbt build --profiles-dir .

reconcile:      ## check the warehouse against an independent pandas implementation
	python scripts/reconcile.py --raw $(OLIST_RAW_DIR) --db $(OLIST_WAREHOUSE_PATH)

sample:         ## write a small synthetic dataset (same schema) to data/sample
	python scripts/make_sample_data.py --out data/sample

build-sample:   ## build + reconcile on the synthetic sample (what CI runs)
	$(MAKE) build reconcile OLIST_RAW_DIR=$(CURDIR)/data/sample OLIST_WAREHOUSE_PATH=$(CURDIR)/warehouse/sample.duckdb

lint:
	ruff check scripts

docs:           ## lineage graph + column docs at http://localhost:8081
	cd transform && dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir . --port 8081

clean:
	rm -rf transform/target transform/logs warehouse/*.duckdb
