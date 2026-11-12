import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Pasta raiz do projeto (um nível acima de pipeline/)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Carrega as variáveis de ambiente do ficheiro .env na raiz do projeto
load_dotenv(os.path.join(RAIZ, ".env"))

USUARIO = os.getenv("DB_USER", "postgres")
SENHA = os.getenv("DB_PASSWORD")
HOST = os.getenv("DB_HOST", "localhost")
PORTA = os.getenv("DB_PORT", "5432")
BANCO = os.getenv("DB_NAME", "postgres")

# Aplica o percent-encoding à palavra-passe (caracteres como ! ou @)
engine = create_engine(f"postgresql+psycopg2://{USUARIO}:{quote_plus(SENHA or '')}@{HOST}:{PORTA}/{BANCO}")
