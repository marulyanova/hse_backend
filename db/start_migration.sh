#!/bin/bash

pgmigrate \
  --conn "postgresql://postgres:postgres@localhost:5432/service" \
  -d migrations \
  --target latest \
  migrate