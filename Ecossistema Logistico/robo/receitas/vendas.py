"""Receita: vendas — gerada de uma gravação em 20/10/2026. Ajuste se o site mudar."""


def baixar(page, ctx):
    page.goto(ctx.url)
    page1 = context.new_page()
    page1.goto("https://www.google.com/search?q=edge&oq=edge&gs_lcrp=EgZjaHJvbWUyBggAEEUYOdIBCDIwMjlqMGo3qAIAsAIA&sourceid=chrome&source=chrome.ob&ie=UTF-8")
    page1.goto("https://www.google.com/sorry/index?continue=https://www.google.com/search%3Fq%3Dedge%26oq%3Dedge%26gs_lcrp%3DEgZjaHJvbWUyBggAEEUYOdIBCDIwMjlqMGo3qAIAsAIA%26sourceid%3Dchrome%26source%3Dchrome.ob%26ie%3DUTF-8%26sei%3DWHbXauqZI6zL5OUPiPKhsAM&q=EgSDbK9bGNns3dYGIjCXxl2J1ajDHKUd1XSLHZsXxPpqbxHkwAUysmqt1vAucIL7gOiyMqRZFmTSR2kWTm8yAVJaAUNgrMTUz-3Sr9ZP")
    page1.locator("iframe[name=\"a-st4mn739u4vx\"]").content_frame.get_by_role("checkbox", name="Não sou um robô").click()
    page1.close()
    page.close()
    # ATENÇÃO: a gravação não pegou o download — refaça clicando em exportar/baixar no fim.
