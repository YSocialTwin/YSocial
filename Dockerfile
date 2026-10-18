# syntax=docker/dockerfile:1

FROM ubuntu:24.04
LABEL maintainer="Giulio Rossetti <giulio.rossetti@gmail.com>" \
      version="1.0" \
      description="This is a Docker image of YSocial" \
      website="https://ysocialtwin.github.io/"

RUN apt-get update
RUN apt-get install -y python3-full python3-pip pipx git build-essential python3-dev libffi-dev screen curl nvidia-utils-550
RUN apt-get purge python3-colorama -y

RUN mkdir /app
COPY . /app
WORKDIR /app
RUN curl -fsSL https://ollama.com/install.sh | sh

RUN git submodule update --init --recursive
RUN pip install --break-system-packages --no-cache-dir -r requirements.txt
# RUN pip install --break-system-packages --no-cache-dir -r external/YClient/requirements_client.txt
# RUN pip install --break-system-packages --no-cache-dir -r external/YServer/requirements_server.txt

# enabling python as default in screen sessions
RUN echo 'alias python="python3"' >> ~/.bashrc
RUN ln -s /usr/bin/python3 /usr/bin/python
#RUN ollama serve &
COPY entrypoint.sh /app/entrypoint.sh
VOLUME ["/app", "/root/.ollama/models"]
ENTRYPOINT ["/app/entrypoint.sh"]




