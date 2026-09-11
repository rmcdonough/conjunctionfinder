FROM public.ecr.aws/lambda/python:3.11

COPY requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app ${LAMBDA_TASK_ROOT}/app
COPY ephe ${LAMBDA_TASK_ROOT}/ephe

# Matches backend/app/ephemeris.py's EPHE_PATH default resolution — set
# explicitly here since /var/task is where the base image lands our files.
ENV EPHE_PATH=${LAMBDA_TASK_ROOT}/ephe

CMD ["app.main.handler"]
