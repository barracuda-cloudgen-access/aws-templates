### Make config

.ONESHELL:
SHELL = bash
.SHELLFLAGS = -eu -c
.PHONY: git-clean lint

### Actions

git-clean:
	@if git diff --exit-code; then
		echo "Git is clean"
	else
		echo "Git changes detected! Check and commit changes"
		exit 1
	fi

lint:
	act -j linter --env-file <(echo "RUN_LOCAL=true")
