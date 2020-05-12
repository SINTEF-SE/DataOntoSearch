#!/bin/bash
. venv/bin/activate
set -o errexit
set -o nounset
set -o pipefail

BASE_PATH=$1
SPEC=$2

python dataontosearch.py evaluate \
    --multisearch-result ${BASE_PATH}/search-results/${SPEC}.txt \
    ${BASE_PATH}/specs/${SPEC}.yaml\
    > ${BASE_PATH}/evaluation-results/${SPEC}.csv
