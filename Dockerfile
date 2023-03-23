FROM python:3.9-slim

# Make flask as working directory
WORKDIR /flask

# Copy core files
#COPY . /flask/
COPY *.py ./
COPY templates/* ./templates/
COPY requirements.txt ./

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install the Python libraries
RUN pip3 install --no-cache-dir -r requirements.txt

EXPOSE 5000

# Start Application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--preload", "wsgi:app"]

