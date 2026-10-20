"""Receita: vendas — gerada de uma gravação em 20/10/2026. Ajuste se o site mudar."""


def baixar(page, ctx):
    page.goto(ctx.url)
    page.locator("frame[name=\"top\"]").content_frame.get_by_text("PromaX Versão: 12.24.00.06 Base: 12.24 Engine: q Login de Usuário Usuário :").click()
    page.goto(ctx.url)
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Usuario\"]").press("CapsLock")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Usuario\"]").fill("L")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Usuario\"]").press("CapsLock")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Usuario\"]").fill("Lazaro ")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Usuario\"]").press("CapsLock")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Usuario\"]").fill(ctx.usuario)
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Usuario\"]").press("CapsLock")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Usuario\"]").press("Tab")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Senha\"]").press("CapsLock")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Senha\"]").fill("L")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Senha\"]").press("CapsLock")
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Senha\"]").fill(ctx.senha)
    page.locator("frame[name=\"top\"]").content_frame.locator("input[name=\"Senha\"]").press("Tab")
    page.locator("frame[name=\"top\"]").content_frame.get_by_role("button", name="Confirma").click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.locator("frame[name=\"top\"]").content_frame.get_by_role("button", name="Confirma").click()
    with page.expect_popup() as page1_info:
        page.locator("frame[name=\"top\"]").content_frame.locator("body").press("Enter")
    page1 = page1_info.value
    page1.close()
    page.frame_locator().locator("#atalho").click()
    page.frame_locator().locator("#atalho").fill("03.02.37")
    with page.expect_popup() as page2_info:
        page.frame_locator().locator("#atalho").press("Enter")
    page2 = page2_info.value
    page2.locator("frame[name=\"rotina\"]").content_frame.locator("select[name=\"quebra1\"]").select_option("14")
    page2.locator("frame[name=\"rotina\"]").content_frame.locator("select[name=\"quebra2\"]").select_option("12")
    page2.locator("frame[name=\"rotina\"]").content_frame.get_by_role("cell", name="Sim").get_by_role("radio").check()
    page2.locator("frame[name=\"rotina\"]").content_frame.locator("input[name=\"dataInicial\"]").click()
    page2.locator("frame[name=\"rotina\"]").content_frame.locator("td:nth-child(2) > table > tbody > tr > td > fieldset > .WindowScreen > tbody > tr:nth-child(4) > td").first.click()
    page2.locator("frame[name=\"rotina\"]").content_frame.locator("input[name=\"dataInicial\"]").fill(ctx.ini_mes_br.replace('/', ''))
    page2.locator("frame[name=\"rotina\"]").content_frame.locator("input[name=\"dataInicial\"]").press("Tab")
    page2.locator("frame[name=\"rotina\"]").content_frame.get_by_role("button", name="Visualizar").click()
    page2.close()
    page.goto(ctx.url)
    page3 = context.new_page()
    page3.goto("edge://newtab/")
    page3.close()
    page.locator("frame[name=\"top\"]").content_frame.get_by_role("img", name="AmBev").click()
    page.close()
    # ATENÇÃO: a gravação não pegou o download — refaça clicando em exportar/baixar no fim.
