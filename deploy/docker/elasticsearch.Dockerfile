FROM docker.elastic.co/elasticsearch/elasticsearch:8.19.10
RUN elasticsearch-plugin install --batch analysis-ik
