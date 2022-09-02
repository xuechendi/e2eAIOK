#!/bin/bash

# set vars
MODEL_NAME="dien"
DATA_PATH="/home/vmagent/app/dataset/amazon_reviews"

# enable oneAPI
source /opt/intel/oneapi/setvars.sh --ccl-configuration=cpu_icc --force

# create ci log dir
hashstr_id=$(date +%Y-%m-%d)_$(echo $RANDOM | md5sum | head -c 8)
tmp_dir="/home/vmagent/app/cicd_logs/e2eaiok_cicd_"$MODEL_NAME"_"$hashstr_id
mkdir -p $tmp_dir

set -e
# lauch e2eAIOK dien
cd /home/vmagent/app/e2eaiok
if [ $USE_SIGOPT == 1 ]; then
  SIGOPT_API_TOKEN=$SIGOPT_API_TOKEN python run_e2eaiok.py --data_path $DATA_PATH --model_name $MODEL_NAME 2>&1 | tee $tmp_dir/e2eaiok_cicd.log
else
  python run_e2eaiok.py --data_path $DATA_PATH --model_name $MODEL_NAME --no_sigopt 2>&1 | tee $tmp_dir/e2eaiok_cicd.log
fi

# store e2eaiok ci logs and data
cp /home/vmagent/app/e2eaiok/e2eaiok.db $tmp_dir/
cp -r /home/vmagent/app/e2eaiok/result $tmp_dir/

# test
LANG=C SIGOPT_API_TOKEN=$SIGOPT_API_TOKEN MODEL_NAME=$MODEL_NAME LOG_FILE=$tmp_dir/e2eaiok_cicd.log tests/cicd/bats/bin/bats tests/cicd/test_log_format.bats
LANG=C SIGOPT_API_TOKEN=$SIGOPT_API_TOKEN MODEL_NAME=$MODEL_NAME DATA_PATH=$DATA_PATH CUSTOM_RESULT_PATH=$tmp_dir tests/cicd/bats/bin/bats tests/cicd/test_result_exist.bats
LANG=C SIGOPT_API_TOKEN=$SIGOPT_API_TOKEN MODEL_NAME=$MODEL_NAME DATA_PATH=$DATA_PATH CUSTOM_RESULT_PATH=$tmp_dir tests/cicd/bats/bin/bats tests/cicd/test_model_reload.bats