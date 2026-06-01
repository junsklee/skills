# Deployment

## Local runtime model

- Source edits happen in `~/cubrid-testtools-internal/qaresult_enhance`
- The local server runs from `~/qaresult_en`
- Env-specific files come from `~/qaresult_en_260114`, and if not found, should be selected snapshot under `~/qaresult_en_*`
- Tomcat lives in `~/apache-tomcat-8.5.4`

## Required env-specific files

These files are restored from the chosen env snapshot after copying the repo tree:

- `build.xml`
- `src/conf/constant.properties`
- `src/conf/datasource/sql-map-qaresult.properties`
- `src/conf/log4j.xml`
- `src/conf/mask_keywords.txt`

## Normal deploy sequence

Use the helper script:

```bash
~/skills/maintain-qaresult-enhance/scripts/deploy-local-qahome.sh \
  --env-source ~/qaresult_en_260126
```

Use `--dry-run` to print the exact commands without executing them.

## Equivalent manual flow

```bash
cd ~/ && cp -r cubrid-testtools-internal/qaresult_enhance/* qaresult_en/
cd ~ && cp "$ENV_SOURCE"/src/conf/constant.properties qaresult_en/src/conf/constant.properties
cd ~ && cp "$ENV_SOURCE"/src/conf/datasource/sql-map-qaresult.properties qaresult_en/src/conf/datasource/sql-map-qaresult.properties
cd ~ && cp "$ENV_SOURCE"/src/conf/log4j.xml qaresult_en/src/conf/log4j.xml
cd ~ && cp "$ENV_SOURCE"/src/conf/mask_keywords.txt qaresult_en/src/conf/mask_keywords.txt
cd ~ && cp "$ENV_SOURCE"/build.xml qaresult_en/build.xml
~/apache-tomcat-8.5.4/bin/shutdown.sh
cd ~/qaresult_en && ant
~/apache-tomcat-8.5.4/bin/startup.sh
```

## Snapshot selection

Use `~/qaresult_en_260114` as the snapshot, with the following as backup:

- `~/qaresult_en_260126`
- `~/qaresult_en_260126_1`
- `~/qaresult_en_qaresult_en_260211`

## After restart

- Load the affected page or endpoint from the local QAHome instance
- Check `~/apache-tomcat-8.5.4/logs/` for startup or runtime errors
- Re-check that the env-specific files were not overwritten by source-tree defaults during the copy step
