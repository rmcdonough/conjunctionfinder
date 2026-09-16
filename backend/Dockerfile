FROM public.ecr.aws/lambda/python:3.14

# pyswisseph and cffi (a timezonefinder dependency) publish no prebuilt
# wheel for this Python version, so pip must build them from source here.
# The base image's Amazon Linux 2023 layer doesn't include a C toolchain by
# default (it does for older Python-version base images that still had
# prebuilt wheels available, which is why this step wasn't needed before).
RUN dnf install -y gcc gcc-c++ make libffi-devel && dnf clean all

COPY requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app ${LAMBDA_TASK_ROOT}/app
COPY ephe ${LAMBDA_TASK_ROOT}/ephe

# The build context's source files are owner-read-only (0600/0700) on this
# machine; Docker COPY preserves that, but the Lambda runtime executes as a
# non-root user that can't read owner-only files. Fix permissions so the
# runtime can actually read the app code and ephemeris data.
RUN chmod -R a+rX ${LAMBDA_TASK_ROOT}/app ${LAMBDA_TASK_ROOT}/ephe

# Matches backend/app/ephemeris.py's EPHE_PATH default resolution — set
# explicitly here since /var/task is where the base image lands our files.
ENV EPHE_PATH=${LAMBDA_TASK_ROOT}/ephe

CMD ["app.main.handler"]
