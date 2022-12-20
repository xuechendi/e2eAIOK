# bash run_inference.sh criteo_small node_ip
# bash run_inference.sh kaggle node_ip
# bash run_inference.sh criteo_full head_node_ip worker_node_ip...
#!/bin/bash
set -e
seed_num=$(date +%s)

# check cmd
echo "check cmd"
if [ "${2}" = "" ]; then
    echo "error: node_ip is None"
fi

if [[ ${1} != "criteo_small" && ${1} != "criteo_full" && ${1} != "kaggle" ]]; then
    echo "error: need to use 'criteo_small' or 'criteo_full' or 'kaggle' mode"
    exit
fi

index=1
for arg in "$@"
    do
        if [ $index \> 1 ]; then
            if [[ ! $arg =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
                echo "error: node_ip<$arg> is invalid"
                exit
            fi
            field1=$(echo $arg|cut -d. -f1)
            field2=$(echo $arg|cut -d. -f2)
            field3=$(echo $arg|cut -d. -f3)
            field4=$(echo $arg|cut -d. -f4)
            if [[ $field1 -gt 255 || $field2 -gt 255 || $field3 -gt 255 || $field4 -gt 255 ]]; then
                echo "error: node_ip<$field1.$field2.$field3.$field4> is invalid"
                exit
            fi
        fi
        let index+=1
    done 

# set files path
hosts_file="../hosts"
config_path_infer="../data_processing/config_infer.yaml"
save_path="../data_processing/data_info.txt"
if [ ! -d $OUTPUT_DIR ]; then
  mkdir $OUTPUT_DIR
fi
log_path="$OUTPUT_DIR/logs"
if [ ! -d $log_path ]; then
  mkdir $log_path
fi

# set parameters
ncpu_per_proc=1
nproc_per_node=2
ccl_worker_count=4
nnodes=$[ $#-1 ]
world_size=$[ ${nnodes}*${nproc_per_node} ]
num_cpus=$(cat /proc/cpuinfo| grep "physical id"| sort| uniq| wc -l)
per_cpu_cores=$(cat /proc/cpuinfo | grep "cpu cores" | uniq | awk -F: '{print $2}')
omp_num_threads=$[ $per_cpu_cores*$num_cpus/$nproc_per_node-$ccl_worker_count ]
nproc=$(ulimit -u -H)
if [ ${nproc} -le 1048576 ] && [ ${omp_num_threads} -gt 12 ]; then
    omp_num_threads=12
fi

# check ray
set +e
ray status > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "OMP_NUM_THREADS: ${omp_num_threads}"
    export OMP_NUM_THREADS=${omp_num_threads}
    echo "ray has been started"
else
    echo "start ray"
    echo "OMP_NUM_THREADS: ${omp_num_threads}"
    echo "clean memory"
    echo never  > /sys/kernel/mm/transparent_hugepage/enabled; sleep 1
    echo never  > /sys/kernel/mm/transparent_hugepage/defrag; sleep 1
    echo always > /sys/kernel/mm/transparent_hugepage/enabled; sleep 1
    echo always > /sys/kernel/mm/transparent_hugepage/defrag; sleep 1
    echo 1 > /proc/sys/vm/compact_memory; sleep 1
    echo 3 > /proc/sys/vm/drop_caches; sleep 1
    need_memory_criteo_small=171798691840
    need_memory_kaggle=10737418240
    unit_memory=42949672960
    avail_memory=$[ $[ $(cat /proc/meminfo | grep MemAvailable | awk -F' ' '{print $2}')*1024 ]-$unit_memory]
    if [ $avail_memory -gt $need_memory_criteo_small ]; then
        obj_memory=$need_memory_criteo_small
    elif [ $avail_memory -gt $need_memory_kaggle ]; then
        obj_memory=$avail_memory
        echo "WARNING: Memory is not enough for 'criteo_small' mode, may cause Ray object spilling. Please use 'kaggle' mode."
    else
        echo "Error: Please make sure the available memory is at least greater than 50G, exit"
        exit
    fi
    echo object-store-memory is $[ $obj_memory/1024/1024/1024 ] GB
    export OMP_NUM_THREADS=${omp_num_threads} && ray start --node-ip-address="${2}" --head --port 5678 --dashboard-host 0.0.0.0 --object-store-memory $obj_memory --system-config='{"object_spilling_threshold":0.98}'
fi

# model inference
echo "start model inference"
cd ./dlrm
infer_start=$(date +%s)
/opt/intel/oneapi/intelpython/latest/envs/pytorch_mlperf/bin/python -u ./launch_inference.py --distributed --config-path=${config_path_infer} --save-path=${save_path}  --ncpu_per_proc=${ncpu_per_proc} --nproc_per_node=${nproc_per_node} --nnodes=${nnodes} --world_size=${world_size} --hostfile ${hosts_file} --master_addr=${2} $dlrm_extra_option 2>&1 | tee $log_path/run_inference_${seed_num}.log

infer_end=$(date +%s)
infer_spend=$(( infer_end - infer_start ))
echo inference time is ${infer_spend} seconds.