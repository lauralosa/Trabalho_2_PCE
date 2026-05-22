# 1. Usa uma imagem oficial do Python
FROM python:3.11-slim

# 2. Define a pasta de trabalho dentro do contentor
WORKDIR /app

# 3. Copia o ficheiro de dependências
COPY requirements.txt .

# 4. Instala as seguintes bibliotecas [cite: 134]
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia o resto do código (Garante o espaço entre os dois pontos!)
COPY . .

# 6. Comando para iniciar a API FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]