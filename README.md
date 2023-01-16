# CoinHub -> Bigdata 
1. Install project 
Install all package in file requirement.txt
> pip install -r requirement.txt
Run docker 
> docker-compose up
Enable safe mode in namenode
> docker exec -it namenode /bin/bash 
> hdfs dfsadmin -safemode leave
> exit
Add hostname to etc/hosts
> 127.0.0.1 datanode-1
Add foler logs in folder consumer, producer
## Run 
Run file producer
> for /f %i in ('python -m certifi') do set SSL_CERT_FILE=%i
> python kafka/producer/app.py
Run file consumer
> python kafka/consumer/app.py