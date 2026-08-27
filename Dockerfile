# Imagem do site. Sem dependencia para instalar: o projeto roda com a
# biblioteca padrao do Python e nada mais.
FROM python:3.11-slim

WORKDIR /app
COPY . /app

# A base fica em volume: o container e descartavel, os dados nao.
VOLUME ["/app/dados"]

EXPOSE 8000
CMD ["python3", "servidor.py", "--host", "0.0.0.0", "--porta", "8000"]
