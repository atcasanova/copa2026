#!/bin/bash

# Script de Atualização e Deploy - Bolão Copa 2026
# Este script deve ser executado no servidor Linux de produção.

# Cores para saída
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sem Cor

echo -e "${YELLOW}==============================================${NC}"
echo -e "${YELLOW}   Iniciando Atualização do Bolão Copa 2026   ${NC}"
echo -e "${YELLOW}==============================================${NC}"

# 1. Obter últimas alterações do Git
echo -e "\n${GREEN}[1/4] Baixando atualizações do repositório Git...${NC}"
git pull
if [ $? -ne 0 ]; then
    echo -e "${RED}Erro ao executar git pull. Verifique a conexão ou conflitos locais.${NC}"
    exit 1
fi

# 2. Garantir que a rede Docker externa existe
echo -e "\n${GREEN}[2/4] Verificando redes Docker...${NC}"
if ! docker network ls --format '{{.Name}}' | grep -q "^megasena_default$"; then
    echo -e "${YELLOW}Rede externa 'megasena_default' não encontrada. Criando rede...${NC}"
    docker network create megasena_default
    if [ $? -ne 0 ]; then
        echo -e "${RED}Falha ao criar a rede docker 'megasena_default'.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Rede 'megasena_default' criada com sucesso.${NC}"
else
    echo -e "Rede externa 'megasena_default' já existe. OK."
fi

# 3. Reconstruir e subir os contêineres Docker
echo -e "\n${GREEN}[3/4] Atualizando e reiniciando contêineres Docker...${NC}"
# Usamos down e up para aplicar as alterações de rede e mapeamento de variáveis do compose
docker compose down
docker compose up -d --build

if [ $? -ne 0 ]; then
    echo -e "${RED}Erro ao inicializar os contêineres com o Docker Compose.${NC}"
    exit 1
fi

# 4. Status final
echo -e "\n${GREEN}[4/4] Verificando status dos serviços...${NC}"
docker compose ps

echo -e "\n${GREEN}==============================================${NC}"
echo -e "${GREEN}         Atualização concluída com sucesso!     ${NC}"
echo -e "${GREEN}==============================================${NC}"
echo -e "Você já pode acessar a aplicação no domínio configurado."
