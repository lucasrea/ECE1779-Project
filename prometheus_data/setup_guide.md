## Setting up prometheus

1. Install latest version of docker  

2. Start up docker engine  

3. Under root directory of project, run following command in terminal:  
    ```
    docker run -d \
    -p 9090:9090 \
    -v <PATH_TO_PROJECT_ROOT_DIRECTORY>/prometheus_data/prometheus.yml:/etc/prometheus/prometheus.yml \
    --add-host host.docker.internal:host-gateway \
    prom/prometheus
    ```
    remember to replace <PATH_TO_PROJECT_ROOT_DIRECTORY> with the actual path  
    
4. All set! You can visit prometheus's backend at http://localhost:9090/