# AgroZap

O **AgroZap** transforma mensagens de campo enviadas por consultores pelo WhatsApp em rascunhos de relatórios agrícolas. O sistema recebe textos, áudios, fotos e localizações, organiza as mensagens em sessões por remetente, transcreve os áudios e extrai informações com inteligência artificial.

Os relatórios reúnem as informações interpretadas, as fotos, as coordenadas e um anexo para conferência das mensagens originais e das evidências utilizadas. HTML, PDF e referências às fontes são armazenados no PostgreSQL.

**Estado do projeto:** em desenvolvimento. O recebimento, o processamento, a recuperação automática de falhas e a geração de rascunhos estão implementados. As interfaces de revisão e administração ainda não fazem parte deste repositório.

## Objetivo

Facilitar o registro de ocorrências agrícolas usando um canal que o consultor já utiliza em campo. Em vez de preencher um relatório durante a visita, ele pode enviar mensagens que serão organizadas e apresentadas posteriormente para conferência.

A interpretação busca identificar as informações relatadas: fazenda, talhão, cultura, estágio de desenvolvimento, observações, hipóteses, recomendações, produtos e doses. Cada informação extraída deve ter uma evidência no texto de origem. O resultado é um **rascunho automático para revisão**, e não uma recomendação agronômica produzida de forma independente pelo sistema.

## Fluxo principal

1. O consultor envia uma mensagem pelo WhatsApp.
2. A Meta encaminha o evento ao webhook do AgroZap.
3. A API valida a assinatura e os dados recebidos, registra a mensagem e a vincula à sessão do remetente.
4. O processamento segue de acordo com o tipo da mensagem:
   - **Texto:** interpretação agrícola pelo modelo configurado no LM Studio.
   - **Áudio:** download, armazenamento, transcrição em português e interpretação do texto transcrito.
   - **Imagem:** download e armazenamento da foto, preservando a legenda recebida.
   - **Localização:** armazenamento da latitude, longitude, nome e endereço, quando informados.
5. A sessão é encerrada após pelo menos 15 minutos de inatividade. Uma nova mensagem com esse intervalo também pode encerrar a sessão anterior e abrir outra.
6. A rotina automática procura sessões fechadas que ainda não possuem relatório.
7. Quando as mídias e as interpretações necessárias estão prontas e válidas, o sistema monta o HTML, gera o PDF e grava o relatório com suas fontes e versão.

A sessão é agrupada por **remetente e intervalo entre mensagens**. Não existe, neste momento, identificação automática de uma visita ou separação de sessões por fazenda e talhão. As interpretações são feitas por mensagem; o relatório reúne os resultados da sessão.

## Funcionalidades implementadas

- Verificação do webhook da Meta e validação da assinatura HMAC-SHA256 dos eventos recebidos.
- Recebimento de mensagens de texto, áudio, imagem e localização.
- Persistência das mensagens com prevenção de duplicação pelo identificador fornecido pela Meta.
- Agrupamento por remetente, com controles de concorrência no PostgreSQL.
- Download e armazenamento de áudios e imagens no banco.
- Transcrição local com faster-whisper, usando o modelo `large-v3` em CPU com precisão `int8`.
- Interpretação pelo LM Studio, validação da estrutura do resultado e conferência das evidências textuais.
- Uma solicitação de correção à IA quando a resposta não passa pela validação.
- Recuperação de downloads, transcrições e interpretações pendentes ou com erro, respeitando limites e intervalos.
- Recuperação de reservas de processamento abandonadas, com verificações de estado e bloqueio.
- Geração de relatórios HTML e PDF com fotos, localização e anexo de conferência.
- Armazenamento de versões do relatório e identificação das mensagens e interpretações utilizadas.

As validações de evidência ajudam a rastrear a origem das informações, mas não substituem a revisão humana da transcrição e da interpretação.

## Arquitetura e tecnologias

| Componente | Responsabilidade |
|---|---|
| Python, FastAPI e Uvicorn | API de recebimento e ciclo de vida da aplicação. |
| WhatsApp Business Platform / Meta | Origem das mensagens e dos arquivos de mídia. |
| PostgreSQL e Psycopg | Persistência, transações, reservas e bloqueios de processamento. |
| faster-whisper | Transcrição local de áudios. |
| LM Studio e HTTPX | Comunicação com o modelo local para interpretação agrícola. |
| Pydantic | Definição e validação da estrutura das interpretações. |
| Jinja2 e WeasyPrint | Montagem do HTML e conversão para PDF. |
| Docker Compose | Ambiente do PostgreSQL com PostGIS instalado. |

O modelo de interpretação é definido por configuração. O processamento da API e do Whisper ocorre no ambiente Python; o servidor do LM Studio é um serviço separado. O Compose atual inicia **somente o banco**, não a API nem o LM Studio.

## Organização do repositório

| Arquivo ou pasta | Finalidade |
|---|---|
| [app/main.py](app/main.py) | Entrada da aplicação, rota de estado e inicialização da rotina automática. |
| [app/webhook.py](app/webhook.py) | Validação e recebimento dos eventos da Meta. |
| [app/database.py](app/database.py) | Acesso ao banco, gravações e controles de processamento. |
| [app/models.sql](app/models.sql) | Definição das tabelas, chaves e restrições. |
| [app/grouping.py](app/grouping.py) | Agrupamento e fechamento de sessões. |
| [app/media.py](app/media.py) | Download de áudios e imagens. |
| [app/transcribe.py](app/transcribe.py) | Transcrição dos áudios. |
| [app/interpret.py](app/interpret.py) | Comunicação com a IA, estrutura dos dados e validação de evidências. |
| [app/recovery.py](app/recovery.py) | Recuperação de tarefas com falha ou interrompidas. |
| [app/retry_policy.py](app/retry_policy.py) | Limites e intervalos das novas tentativas. |
| [app/worker.py](app/worker.py) | Rotina periódica de recuperação, fechamento e geração de relatórios. |
| [app/report.py](app/report.py) | Preparação dos dados, geração e armazenamento dos documentos. |
| [templates/report.html](templates/report.html) | Modelo visual do relatório. |
| [app/identity.py](app/identity.py) e [app/geo.py](app/geo.py) | Estruturas reservadas para identificação de consultores e consultas espaciais; implementação pendente. |
| [compose.yaml](compose.yaml) e [Dockerfile](Dockerfile) | Ambiente do PostgreSQL com PostGIS. |
| [requirements.txt](requirements.txt) | Dependências Python com versões fixadas. |
| tests/ | Pasta reservada para testes; ainda sem suíte automatizada implementada. |

## Banco de dados

As tabelas do projeto usam o prefixo `agrozap_`.

| Tabela | Conteúdo |
|---|---|
| `agrozap_field_sessions` | Remetente, início, última mensagem e estado da sessão. |
| `agrozap_messages` | Identificador, sessão, remetente, tipo, texto, horários e payload recebido. |
| `agrozap_message_audio` | Arquivo de áudio, transcrição, estados, contadores e reservas das tentativas. |
| `agrozap_message_images` | Arquivo de imagem e controles de download. |
| `agrozap_message_locations` | Coordenadas, nome e endereço enviados. |
| `agrozap_message_interpretations` | Histórico das tentativas, texto-fonte, modelo, versões, resultado e erros. |
| `agrozap_session_reports` | HTML, PDF, versão, modelo de apresentação, índice das fontes e data de criação. |

As mídias e os PDFs são armazenados em colunas binárias. O HTML incorpora as imagens usadas no documento. A definição atual guarda as coordenadas como números; a associação espacial automática com talhões ainda está pendente.

Uma mesma sessão pode ter várias versões de relatório. Ao salvar, o sistema reutiliza a última versão se a versão do modelo visual e o índice das fontes forem iguais. A rotina automática busca sessões **sem relatório**; ela não regenera automaticamente todos os documentos existentes após mudanças nas fontes ou no modelo.

## Configuração e execução local

### Pré-requisitos

- Ambiente Python compatível com as dependências. O código utiliza recursos de Python 3.12 ou superior; a compatibilidade das versões fixadas deve ser verificada no ambiente de instalação.
- Docker e Docker Compose, se for utilizado o ambiente de banco fornecido.
- PostgreSQL acessível à aplicação.
- LM Studio com um modelo carregado e servidor HTTP que atenda à rota `/api/v1/chat` usada pelo projeto.
- Conta e aplicativo configurados para receber eventos da WhatsApp Business Platform.
- URL pública HTTPS para a Meta alcançar o webhook.
- Dependências nativas exigidas pelo WeasyPrint no sistema operacional.
- Espaço para o modelo do Whisper e recursos de CPU e memória para a transcrição e a interpretação.

O modelo do Whisper é carregado na inicialização dos módulos da aplicação. Na primeira execução, pode ser necessário baixar os arquivos do modelo.

### Variáveis de ambiente

Crie um arquivo `.env` local na raiz do projeto. Ele está excluído do Git. Configure as seguintes variáveis sem publicar credenciais no repositório:

| Variável | Finalidade |
|---|---|
| `POSTGRES_HOST` | Endereço do PostgreSQL visto pela aplicação Python. |
| `POSTGRES_PORT` | Porta do banco. No Compose fornecido, a porta publicada no host é `5433`; a interna do contêiner é `5432`. |
| `POSTGRES_DB` | Nome do banco. O Compose define `agrozap`. |
| `POSTGRES_USER` | Usuário do banco. Deve corresponder ao usuário configurado no ambiente; o Compose atual define `dvlp-inteva`. |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL, também utilizada pelo Compose. |
| `META_VERIFY_TOKEN` | Token definido para a verificação inicial do webhook. |
| `META_APP_SECRET` | Segredo do aplicativo Meta, usado na validação das assinaturas. |
| `META_ACCESS_TOKEN` | Token para consultar e baixar mídias na Meta. |
| `META_GRAPH_VERSION` | Versão da Graph API usada nas requisições, no formato esperado pela URL da Meta. |
| `LOCAL_LLM_BASE_URL` | Endereço base do servidor do LM Studio, sem acrescentar `/api/v1/chat`, pois o código adiciona esse caminho. |
| `LOCAL_LLM_MODEL` | Identificador do modelo utilizado pelo servidor de interpretação. |

### Sequência de preparação

1. Obtenha o repositório, crie um ambiente virtual Python e instale as dependências listadas em `requirements.txt`.
2. Prepare o arquivo `.env` com as configurações do ambiente.
3. Inicie o serviço `postgres` definido em `compose.yaml`, ou disponibilize um PostgreSQL próprio.
4. Em um banco novo, execute `app/models.sql` para criar as tabelas. O Compose atual não executa esse arquivo automaticamente. Para bancos existentes, aplique uma migração compatível com o esquema atual: o arquivo contém criação de tabelas, não uma atualização automática de versões anteriores.
5. Inicie o servidor do LM Studio e disponibilize o modelo indicado em `LOCAL_LLM_MODEL`.
6. Na raiz do repositório, execute a aplicação pelo Uvicorn com o destino ASGI `app.main:app`. Defina o endereço e a porta de escuta conforme o ambiente.
7. Verifique a rota `/status` e configure na Meta a URL pública terminada em `/webhook`, usando o mesmo token de verificação do ambiente.
8. Envie mensagens de teste e acompanhe os registros e estados de processamento no banco e nos logs.

O Dockerfile deste repositório prepara o banco; ele não é uma imagem de execução da API Python.

## Endpoints disponíveis

| Método e rota | Finalidade |
|---|---|
| `GET /status` | Informa que a API está respondendo. Não testa a disponibilidade do PostgreSQL, da Meta ou do LM Studio. |
| `GET /webhook` | Responde à verificação inicial do webhook da Meta. |
| `POST /webhook` | Recebe e valida eventos de mensagens. |

A confirmação de recebimento do webhook ocorre após a gravação das mensagens e antes da conclusão das tarefas em segundo plano. Essa confirmação não significa que a transcrição, a interpretação ou o relatório já tenham terminado.

Não há, atualmente, endpoints próprios para listar, baixar, aprovar ou enviar relatórios.

## Recuperação automática de falhas

A rotina é iniciada junto com a API. Ela fecha sessões inativas, recupera tarefas abandonadas, repete trabalhos elegíveis e tenta gerar os relatórios pendentes. Depois de concluir um ciclo, aguarda 60 segundos antes do próximo; o intervalo real entre verificações também depende do tempo gasto no processamento.

| Política atual | Valor |
|---|---|
| Limite de tentativas de download | 5, incluindo a inicial. |
| Limite de tentativas de transcrição | 5, incluindo a inicial. |
| Limite de tentativas de interpretação | 5 por combinação de mensagem, texto-fonte, modelo, prompt e esquema. |
| Espera mínima entre tentativas | 60 segundos. |
| Limiar para avaliar uma reserva como antiga | 300 segundos, com verificações adicionais de bloqueio e estado antes da liberação. |

Esses valores ficam em `app/retry_policy.py`. Downloads e transcrições usam contadores e tokens de reserva; interpretações preservam o histórico de tentativas em linhas separadas. O PostgreSQL também é usado para coordenar o acesso às tarefas.

Relatórios aguardam os dados necessários e não são emitidos pelo fluxo atual quando há erro impeditivo no processamento. Ao atingir o limite de tentativas, a tarefa deixa de ser elegível à recuperação automática e requer investigação. Não há uma interface de reprocessamento manual neste repositório.

## Escopo atual e próximos passos

- As fotos são anexadas ao relatório; não existe análise visual de imagens por IA no fluxo atual.
- O texto e a transcrição são interpretados individualmente, sem uma etapa de consolidação contextual de toda a conversa pela IA.
- O reconhecimento cadastral do consultor e a associação espacial com talhões ainda não estão implementados.
- Telas de agrônomo e administrador, revisão, aprovação e envio do relatório são etapas futuras. Uma integração com Ignition pode utilizar o PostgreSQL, mas o projeto de telas e seus mecanismos de ações ainda não fazem parte deste repositório.
- O armazenamento em Markdown com geração sob demanda é uma possibilidade discutida; o código atual armazena HTML e PDF.
- O processamento periódico roda no mesmo processo da API, sem um serviço independente de fila. A capacidade para carga simultânea depende dos recursos do ambiente e precisa ser medida.
- A pasta de testes ainda não contém uma suíte automatizada. Este README descreve a implementação existente; não representa uma validação de implantação ou carga.

## Licença

Distribuído sob a [licença MIT](LICENSE).
