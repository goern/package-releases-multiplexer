# Package Releases Multiplexer

This will send newly detected package releases to a Kafka Topic.

```shell
pipenv install
DEBUG=1 ./app.py &
faust -A dumper worker
```
