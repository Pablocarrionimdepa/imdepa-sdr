# Imdepa SDR Agent — Fernanda

Aplicação web completa para um agente de SDR (Sales Development Representative) em formato de chatbot, chamada **Fernanda**. Desenvolvida em Python com o framework FastAPI, projetada para ser facilmente instalada e executada em um ambiente Windows Server.

O chatbot utiliza a API da OpenAI (modelo `gpt-4.1-mini`) para conduzir conversas naturais, qualificar leads e coletar informações essenciais, que são armazenadas em um banco de dados SQLite. A aplicação também inclui um painel administrativo para visualização e gerenciamento dos leads capturados.

---

## Funcionalidades

- **Chat com IA:** Conversas inteligentes e naturais seguindo o roteiro SDR da Imdepa.
- **Qualificação de Leads:** Coleta automática de empresa, contato, CNPJ, segmento, produtos, volume, fornecedor, dores e decisores.
- **Banco de Dados SQLite:** Armazenamento simples, sem necessidade de servidores externos.
- **Painel Administrativo:** Interface em `/leads` para visualizar, filtrar, buscar e exportar leads em CSV.
- **Interface Responsiva:** Design com identidade visual Imdepa (vermelho institucional, fonte DM Sans).

---

## Estrutura do Projeto

```
imdepa-sdr-python/
├── app.py                  # Aplicação principal FastAPI
├── ai_agent.py             # Módulo de integração com a OpenAI
├── database.py             # Módulo de gerenciamento do banco SQLite
├── requirements.txt        # Dependências Python
├── .env.example            # Exemplo de variáveis de ambiente
├── README.md               # Este arquivo
├── static/
│   ├── css/                # Arquivos de estilo
│   ├── js/                 # Arquivos JavaScript
│   └── img/                # Imagens e ícones
└── templates/
    ├── chat.html           # Página do chat
    └── leads.html          # Painel de leads
```

---

## Instalação no Windows Server

### Pré-requisitos

- **Python 3.8 ou superior** — baixe em [python.org](https://www.python.org/downloads/). Marque a opção "Add Python to PATH" durante a instalação.
- **Acesso à Internet** — necessário para instalar dependências e comunicar com a API da OpenAI.
- **Chave da API OpenAI** — obtenha em [platform.openai.com](https://platform.openai.com/api-keys).

### Passo 1 — Copiar os Arquivos

Copie toda a pasta `imdepa-sdr-python` para um local no servidor, por exemplo:

```
C:\apps\imdepa-sdr
```

### Passo 2 — Criar Ambiente Virtual

Abra o **Prompt de Comando (CMD)** ou **PowerShell** e execute:

```bash
cd C:\apps\imdepa-sdr

python -m venv venv

.\venv\Scripts\activate
```

Após a ativação, você verá `(venv)` no início da linha do terminal.

### Passo 3 — Instalar Dependências

Com o ambiente virtual ativado:

```bash
pip install -r requirements.txt
```

### Passo 4 — Configurar Variáveis de Ambiente

1. Renomeie o arquivo `.env.example` para `.env`
2. Abra o `.env` em um editor de texto e insira sua chave:

```ini
OPENAI_API_KEY="sua_chave_openai_aqui"
```

### Passo 5 — Executar a Aplicação

```bash
uvicorn app:app --host 0.0.0.0 --port 9095
```

A aplicação estará disponível em:

| Página | URL |
|---|---|
| **Chat da Fernanda** | `http://localhost:9095/` |
| **Painel de Leads** | `http://localhost:9095/leads` |

Para acessar de outras máquinas na rede, substitua `localhost` pelo IP do servidor.

---

## Uso

- **Chat:** Acesse a URL principal para conversar com a Fernanda. Os leads são salvos automaticamente.
- **Painel de Leads:** Acesse `/leads` para visualizar, filtrar e exportar os dados coletados.

Para parar a aplicação, pressione `Ctrl + C` no terminal.
