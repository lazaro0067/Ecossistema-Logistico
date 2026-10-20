"""Receita: ressuprimento (Power BI) — gravada em 20/10/2026 e limpa. Ajuste se o relatório mudar."""


def baixar(page, ctx):
    page.goto(ctx.url)
    ctx.login_microsoft(page)  # se pedir login: e-mail, senha e o código do celular (abre uma janelinha)
    if "powerbi.com" in page.url and "reports" not in page.url:
        page.goto(ctx.url)
    # espera o relatório carregar e abre o "⋯ Mais opções" do visual (o botão só aparece com o mouse em cima)
    botao = page.get_by_test_id("visual-more-options-btn").first
    botao.wait_for(state="attached")
    page.wait_for_timeout(3000)
    botao.click(force=True)
    page.get_by_test_id("pbimenu-item.Exportar dados").click()
    page.get_by_role("radio", name="Dados com layout atual").check()
    with page.expect_download() as download_info:
        page.get_by_test_id("export-btn").click()
    download = download_info.value
    return ctx.salvar(download)
