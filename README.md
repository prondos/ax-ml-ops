# MLOps application stack

This project shows how you may integrate some of the popular tools to perform Data Science experiments.


## Components

* **S3 (Minio)** exposed at http://localhost:9000

* **Airflow** exposed at http://localhost:8000

* **Jupyter notebook** exposed at http://localhost:8800

* **MLFlow** exposed at http://localhost:5000

* **Optuna dashboard** exposed at http://localhost:8080

* **PostgreSQL**

* **RabbitMQ**


## Usage scenario

1. Start **ax-ml-ops** application stack with
    ```shell
    ./stack-up.sh
    ```

2. Enable following pipelines in **Airflow**

    * kaggle-spaceship-titanic-data

    * kaggle-spaceship-titanic-model


3. Execute *kaggle-spaceship-titanic-data* pipeline with **Airflow**

4. Monitor key metrics with **MLFlow**

5. Monitor model hyperparameter tuning with **Optuna dashboard**

6. Stop **ax-ml-ops** application stack and remove all its assets (without images) with
    ```shell
    ./stack-down.sh
    ```




