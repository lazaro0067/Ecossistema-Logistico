"""Receita: ressuprimento (Power BI) — gravada em 20/10/2026 e limpa. Ajuste se o relatório mudar."""


def _abrir_menu_do_visual(page, tentativas: int = 60):
    """O botão "⋯ Mais opções" da tabela só existe com o mouse em cima: passa o mouse sobre a tabela até ele
    aparecer (o relatório pode demorar para desenhar)."""
    botao = page.get_by_test_id("visual-more-options-btn").first
    visual = page.locator("visual-container, .visual-container, .visualContainerHost").first
    for _ in range(tentativas):
        try:
            if visual.count():
                visual.hover(timeout=3000, force=True)
            else:
                page.mouse.move(450, 420)  # meio da tabela da esquerda (tela de 1440 x 900)
            page.mouse.move(452, 425)
        except Exception:  # noqa: BLE001 — ainda carregando
            pass
        page.wait_for_timeout(1500)
        if botao.count():
            botao.click(force=True)
            return
    raise TimeoutError("O relatório não mostrou o botão '⋯ Mais opções' da tabela.")


def baixar(page, ctx):
    page.goto(ctx.url)
    ctx.login_microsoft(page)  # se pedir login: e-mail, senha e o código do celular (abre uma janelinha)
    if "powerbi.com" in page.url and "reports" not in page.url:
        page.goto(ctx.url)
    page.wait_for_timeout(5000)
    _abrir_menu_do_visual(page)
    page.get_by_test_id("pbimenu-item.Exportar dados").click()
    page.get_by_role("radio", name="Dados com layout atual").check()
    with page.expect_download() as download_info:
        page.get_by_test_id("export-btn").click()
    download = download_info.value
    return ctx.salvar(download)
