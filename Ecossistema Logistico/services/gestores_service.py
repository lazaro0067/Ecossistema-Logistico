"""Gente › 👔 Gestores — cadastro dos gestores (donos de departamento e de contas do OBZ).

Depois de cadastrado, o gestor pode ganhar acesso ao sistema (vira usuário, perfil Gestor) e ser vinculado como
dono de um departamento do OBZ e sub-dono de contas (💰 Financeiro › 👤 Donos).
"""
import pandas as pd

from core import tempo
from database.connection import execute, query_df, query_one
from services.erros import RegraNegocioError

PERMISSOES_GESTOR = ["financeiro.obz_gestao", "financeiro.obz_le", "financeiro.obz_tend", "financeiro.obz_reuniao",
                     "financeiro.obz_aprov"]


def listar(so_ativos: bool = False) -> pd.DataFrame:
    df = query_df("""SELECT g.*, u.email AS login_acesso, u.ativo AS acesso_ativo FROM gestores g
                     LEFT JOIN usuarios u ON u.id = g.usuario_id""" + (" WHERE g.ativo = 1" if so_ativos else "")
                  + " ORDER BY g.nome")
    return df


def nomes() -> dict[int, str]:
    df = listar(so_ativos=True)
    return {int(i): n for i, n in zip(df["id"], df["nome"])}


def buscar(gid: int) -> dict | None:
    return query_one("SELECT * FROM gestores WHERE id = ?", (int(gid),))


def salvar(gid: int | None, nome: str, cargo: str = "", email: str = "", telefone: str = "",
           departamento: str = "", ativo: bool = True) -> int:
    nome = (nome or "").strip()
    if not nome:
        raise RegraNegocioError("Informe o nome do gestor.")
    dados = (nome, (cargo or "").strip(), (email or "").strip().lower(), (telefone or "").strip(),
             (departamento or "").strip(), 1 if ativo else 0)
    if gid:
        execute("UPDATE gestores SET nome = ?, cargo = ?, email = ?, telefone = ?, departamento = ?, ativo = ? "
                "WHERE id = ?", (*dados, int(gid)))
        return int(gid)
    return execute("INSERT INTO gestores (nome, cargo, email, telefone, departamento, ativo, criado_em) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)", (*dados, tempo.agora().strftime("%Y-%m-%d %H:%M")))


def excluir(gid: int) -> None:
    execute("DELETE FROM obz_resp WHERE gestor_id = ?", (int(gid),))
    execute("UPDATE obz_areas SET dono_gestor_id = NULL WHERE dono_gestor_id = ?", (int(gid),))
    execute("DELETE FROM gestores WHERE id = ?", (int(gid),))


def criar_acesso(gid: int, operacoes: list[int], enviar_email: bool = True) -> dict:
    """Cria o usuário do gestor (login = e-mail) com acesso à Gestão OBZ e vincula ao cadastro."""
    from services import usuarios_service

    g = buscar(gid)
    if not g:
        raise RegraNegocioError("Gestor não encontrado.")
    if g.get("usuario_id"):
        raise RegraNegocioError("Este gestor já tem acesso.")
    if not g.get("email"):
        raise RegraNegocioError("Cadastre o e-mail do gestor antes de criar o acesso (é o login).")
    r = usuarios_service.salvar_usuario(id=None, nome=g["nome"], senha="", email=g["email"],
                                        cargo=g.get("cargo") or "Gestor", perfil="Gestor", e_aprovador=False,
                                        alcada=0.0, ativo=True, trocar_senha=True, permissoes=PERMISSOES_GESTOR,
                                        operacoes=operacoes, enviar_email=enviar_email)
    execute("UPDATE gestores SET usuario_id = ? WHERE id = ?", (r["id"], int(gid)))
    return r


def vincular_usuario(gid: int, usuario_id: int | None) -> None:
    execute("UPDATE gestores SET usuario_id = ? WHERE id = ?", (usuario_id, int(gid)))


def gestor_do_usuario(usuario_id: int) -> int | None:
    r = query_one("SELECT id FROM gestores WHERE usuario_id = ? AND ativo = 1", (int(usuario_id),))
    return int(r["id"]) if r else None


# --- 👤 Donos do OBZ escolhidos pelos acessos do sistema ---------------------------------------------------------
def gestor_de_usuario(usuario_id: int) -> int:
    """Gestor (dono do OBZ) ligado a este acesso. Sem vínculo: liga o gestor de mesmo e-mail ou cria um novo
    com o nome/e-mail do usuário — o resto do OBZ (tendências, críticas, alertas) continua usando o gestor."""
    g = query_one("SELECT id, ativo FROM gestores WHERE usuario_id = ? ORDER BY ativo DESC, id", (int(usuario_id),))
    if g:
        if not g["ativo"]:
            execute("UPDATE gestores SET ativo = 1 WHERE id = ?", (int(g["id"]),))
        return int(g["id"])
    u = query_one("SELECT id, nome, email, cargo FROM usuarios WHERE id = ?", (int(usuario_id),))
    if not u:
        raise RegraNegocioError("Usuário não encontrado.")
    email = (u.get("email") or "").strip().lower()
    if email:
        g = query_one("SELECT id FROM gestores WHERE LOWER(email) = ? AND usuario_id IS NULL", (email,))
        if g:
            execute("UPDATE gestores SET usuario_id = ?, ativo = 1 WHERE id = ?", (int(usuario_id), int(g["id"])))
            return int(g["id"])
    gid = salvar(None, u["nome"], u.get("cargo") or "", email)
    execute("UPDATE gestores SET usuario_id = ? WHERE id = ?", (int(usuario_id), int(gid)))
    return int(gid)


def usuario_do_gestor() -> dict[int, int]:
    """{gestor_id: usuario_id} dos gestores ligados a um acesso."""
    df = query_df("SELECT id, usuario_id FROM gestores WHERE usuario_id IS NOT NULL")
    return {int(g): int(u) for g, u in zip(df["id"], df["usuario_id"])}


def liberar_telas_obz(usuario_id: int) -> bool:
    """Dá ao dono as telas do OBZ que ele precisa (painel, L.E, tendências, reunião, justificativas) se ainda não
    tiver. Não mexe em quem já tem a pasta Financeiro inteira nem no Master. Devolve True se liberou algo."""
    from database.connection import get_conn

    u = query_one("SELECT perfil FROM usuarios WHERE id = ?", (int(usuario_id),))
    if not u or u["perfil"] == "Master":
        return False
    tem = set(query_df("SELECT modulo FROM usuario_modulos WHERE usuario_id = ?", (int(usuario_id),))["modulo"])
    if "financeiro" in tem:
        return False
    faltam = [p for p in PERMISSOES_GESTOR + ["financeiro.obz_just"] if p not in tem]
    if not faltam:
        return False
    with get_conn() as conn:
        conn.executemany("INSERT INTO usuario_modulos (usuario_id, modulo) VALUES (?, ?)",
                         [(int(usuario_id), p) for p in faltam])
    return True
