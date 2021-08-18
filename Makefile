### Make config

.ONESHELL:
SHELL = bash
.SHELLFLAGS = -eu -c
.PHONY: upload git-clean lint template-set template-run template-test

### Variables

MARKETPLACE_PATH = ./helpers/marketplace-template
MARKETPLACE_SCRIPT = main.py
S3_BUCKET = fyde-cloudformation-store
PYTHON_VENV_PATH = ./.venv

### Actions

upload: template-test template-run
	$(MARKETPLACE_PATH)/$(MARKETPLACE_SCRIPT)
	aws s3 cp \
		--recursive \
		--exclude "*" \
		--include "*.yaml" \
		./templates/ s3://$(S3_BUCKET)/
	aws s3 cp \
		--recursive \
		--exclude "*" \
		--include "*.png" \
		./misc/ s3://$(S3_BUCKET)/misc/

git-clean:
	@if git diff --exit-code; then
		echo "Git is clean"
	else
		echo "Git changes detected! Check and commit changes"
		exit 1
	fi

lint:
	find ./helpers -name "*.py" -type f -print0 \
		-exec black {} --verbose \; \
		-exec isort {} --show-files \;
	act -j linter --env-file <(echo "RUN_LOCAL=true")

template-set:
	python3 -m venv $(PYTHON_VENV_PATH)
	source $(PYTHON_VENV_PATH)/bin/activate
	pip3 install -r $(MARKETPLACE_PATH)/requirements.txt

template-run: template-set
	source $(PYTHON_VENV_PATH)/bin/activate
	$(MARKETPLACE_PATH)/$(MARKETPLACE_SCRIPT)

template-test: template-set
	source $(PYTHON_VENV_PATH)/bin/activate
	$(MARKETPLACE_PATH)/$(MARKETPLACE_SCRIPT) --no-creds \
		--out $(MARKETPLACE_PATH)/test/aws-cf-asg-marketplace-test.yaml
