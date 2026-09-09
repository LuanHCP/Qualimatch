from database import DB_PATH, init_db

if __name__ == "__main__":
    path = init_db(reset=True)
    print(f"Banco de demonstração recriado: {path}")
