FROM mcr.microsoft.com/devcontainers/python:3.10

# Mise à jour et installation de Java 17 (plus facile à trouver sur les images récentes)
RUN apt-get update && apt-get install -y default-jdk-headless \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# On cherche dynamiquement le chemin de Java pour éviter les erreurs de chemin
ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH=$PATH:$JAVA_HOME/bin

# Installation de PySpark et des outils nécessaires
RUN pip install --no-cache-dir pyspark findspark pandas matplotlib
