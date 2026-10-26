from sqlalchemy import text

# Data e hora do servidor em UTC (RNF13), preenchida pelo banco.
# Declarar como server_default no model faz o ORM omitir a coluna no INSERT
# quando o valor é None, em vez de mandar NULL.
AGORA_UTC = text("(now() AT TIME ZONE 'utc')")
