import db


def log(user, action, entity, entity_id=None, detail=None, ip=None):
    db.execute(f"""
        INSERT INTO audit_log (user_id, user_nome, action, entity, entity_id, detail, ip)
        VALUES ({db.lit(user['id']) if user else 'NULL'}, {db.lit(user['nome']) if user else 'NULL'},
                {db.lit(action)}, {db.lit(entity)}, {db.lit(str(entity_id) if entity_id is not None else None)},
                {db.json_lit(detail) if detail is not None else 'NULL'}, {db.lit(ip)});
    """)
