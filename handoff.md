# Handoff: Compartilhamento de Rankings e Prêmio Lúcido

Este documento fornece as diretrizes arquiteturais, a estrutura de arquivos e o funcionamento do mecanismo de exportação e compartilhamento de rankings e palpites como imagem (PNG) no Bolão Copa 2026.

## 📋 Visão Geral do Compartilhamento

A exportação de tabelas de ranking no bolão é feita **exclusivamente no lado do cliente (client-side)**. Não existem rotas de backend dedicadas a converter HTML/CSS em imagem ou gerar PDFs. 

Para que a exportação funcione e se pareça exatamente com o layout do site (mesmo em telas pequenas onde as tabelas ficam responsivas ou condensadas), é usada uma técnica de renderização baseada em SVG e Canvas.

---

## 🛠️ Como Funciona o Exportador (`ExportElementImageButton.jsx`)

O componente principal responsável por essa funcionalidade é o [ExportElementImageButton](file:///opt/stacks/copa2026/frontend/src/components/ExportElementImageButton.jsx). Ele recebe uma referência React (`targetRef`) apontando para o elemento DOM que deve ser transformado em imagem.

O fluxo de exportação segue as seguintes etapas:
1. **Clone do Elemento**: O nó DOM do ranking/card é clonado.
2. **Cópia de Estilos Computados (`copyComputedStyles`)**: Como os estilos CSS vêm de classes MUI dinâmicas e stylesheets globais, a função copia recursivamente todos os estilos computados do elemento original para as tags clonadas do novo nó.
3. **Limpeza de Imagens (`prepareImagesForExport`)**:
   > [!WARNING]
   > Recursos de imagem remotos ou relativos (tags `<img>`) costumam quebrar a serialização XML do SVG ou violar regras de CORS ao desenhar no Canvas. Para contornar isso, a função remove (ou oculta) todas as tags `<img>` do clone antes da renderização.
4. **Serialização em SVG**: O clone é serializado como uma string XML e inserido dentro de um bloco `<foreignObject>` de um SVG inline.
5. **Conversão SVG para Imagem e Canvas**: O SVG é carregado como uma Data URL em um objeto `Image`. Esta imagem é então desenhada em um elemento `<canvas>` ajustado pelo pixel ratio da tela (`devicePixelRatio`).
6. **Download / Compartilhamento**: 
   - Se o navegador suportar a API Web Share (`navigator.share`), a imagem PNG é empacotada em um arquivo temporário e enviada nativamente para aplicativos como o WhatsApp.
   - Caso contrário, é feito o fallback de download direto criando um link dinâmico com atributo `download`.

---

## 🏗️ Arquitetura dos Rankings e Containers Offscreen

Muitos rankings e tabelas exibidos na tela principal possuem botões de compartilhamento ("Compartilhar Top 10"). Para garantir que o PNG gerado tenha um layout bonito, de tamanho fixo e bem formatado (independentemente do tamanho da janela de visualização do usuário), nós usamos **containers fora da área visível (off-screen)** dedicados para a exportação.

Esses elementos ficam escondidos usando posicionamento absoluto negativo em um Box invisível:

```javascript
<Box
  sx={{
    position: 'absolute',
    left: -10000,
    top: 0,
    width: 760,
    bgcolor: 'background.paper'
  }}
  aria-hidden="true"
>
  {/* Card para o Ranking Geral */}
  <Card ref={generalTop10Ref}>...</Card>

  {/* Card para o Prêmio Lúcido */}
  <Card ref={lucidoTop10Ref} sx={{ mt: 3 }}>...</Card>
</Box>
```

Dessa forma, o componente de exportação renderiza um elemento com largura fixa (`760px`) e layout previsível, evitando barras de rolagem ou quebras de linha indesejadas na imagem gerada.

---

## 🤡 Prêmio Lúcido e Critérios de Desempate

O Prêmio Lúcido lista os participantes com mais palpites que renderam exatamente 0 pontos.

### Regras de Negócio e Desempate (Ordem de Prioridade)
1. **Quantidade de palpites com 0 pontos** (Ordem decrescente, quem tem mais lidera).
2. **Diferença acumulada de gols nos palpites de 0 pontos** (Ordem decrescente). Se o palpite foi `0x3` e o placar oficial foi `1x0`, a diferença absoluta de gols é `abs(0 - 1) + abs(3 - 0) = 4`. Quem errar por uma diferença de gols maior fica na frente.
3. **Data/Hora de cadastro no sistema** (Ordem cronológica crescente, mais antigo primeiro).
4. **Nome de exibição** (Ordem alfabética).

### Backend e Cache
Toda a lógica de consulta e ordenação é controlada pela função [get_lucido_ranking](file:///opt/stacks/copa2026/backend/app/scoring.py#L511) e disponibilizada pelas rotas `/api/rankings/lucido/general` e `/api/rankings/lucido/group/{group_id}` em [rankings.py](file:///opt/stacks/copa2026/backend/app/routers/rankings.py). A invalidação de cache atinge o banco e limpa todas as entradas (inclusive lucido) de forma uniforme.

---

## 📂 Arquivos Importantes Relacionados

* **Frontend**:
  * [ExportElementImageButton.jsx](file:///opt/stacks/copa2026/frontend/src/components/ExportElementImageButton.jsx): Motor de renderização e compartilhamento de imagem.
  * [Rankings.jsx](file:///opt/stacks/copa2026/frontend/src/pages/Rankings.jsx): Exibe e exporta o ranking normal e o Prêmio Lúcido.
  * [Predictions.jsx](file:///opt/stacks/copa2026/frontend/src/pages/Predictions.jsx): Onde é exibido o subtítulo `"🤡 Prêmio Lúcido"` no modal de distribuição de palpites com 0 pontos após o fim de cada jogo.
  * [GroupDetails.jsx](file:///opt/stacks/copa2026/frontend/src/pages/GroupDetails.jsx): Implementa compartilhamento de ranking específico para grupos de amigos.

* **Backend**:
  * [scoring.py](file:///opt/stacks/copa2026/backend/app/scoring.py): Contém os cálculos matemáticos dos rankings e a manipulação do cache.
  * [schemas.py](file:///opt/stacks/copa2026/backend/app/schemas.py): Define o modelo de payload `LucidoRankingRowResponse`.
  * [test_core.py](file:///opt/stacks/copa2026/backend/app/tests/test_core.py): Testes unitários focados na validação das regras de negócio (incluindo o caso `test_lucido_ranking_flow`).

---

## 🎯 Próximos Passos Sugeridos / Ideias de Melhoria
1. **Otimização de Imagens no Compartilhamento**: Se necessário incluir imagens ou avatares no export, investigar a conversão das imagens locais e avatares em strings em Base64 antes da exportação para contornar a regra que remove tags `<img>`.
2. **Histórico Lúcido**: Adicionar uma visualização em gráfico ou histórico no fim da página que simule a evolução do Prêmio Lúcido de forma semelhante ao gráfico de evolução do ranking geral.
