#!/bin/bash
# тоже изменен порт с 5432 на 5435

pgmigrate \
  --conn "postgresql://postgres:postgres@localhost:5435/service" \
  -d migrations \
  --target latest \
  migrate