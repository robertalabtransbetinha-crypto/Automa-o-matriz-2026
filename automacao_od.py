
import streamlit as st
import pandas as pd
import requests
import time
import io
import re

# ============================================================
# GOOGLE ROUTES API
# ============================================================

URL_ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"

FIELD_MASK = "routes.distanceMeters,routes.duration"


def montar_ponto(valor):
    """
    Aceita cidades, endereços ou coordenadas.
    Coordenadas devem estar no formato latitude, longitude.
    Exemplo: -27.5954, -48.5480
    """
    if pd.isna(valor) or not str(valor).strip():
        raise ValueError("Origem ou destino está vazio.")

    texto = str(valor).strip()

    coordenadas = re.fullmatch(
        r"\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*"
        r"(-?\d+(?:\.\d+)?)\s*",
        texto
    )

    if coordenadas:
        latitude = float(coordenadas.group(1))
        longitude = float(coordenadas.group(2))

        if not -90 <= latitude <= 90:
            raise ValueError("Latitude inválida.")

        if not -180 <= longitude <= 180:
            raise ValueError("Longitude inválida.")

        return {
            "location": {
                "latLng": {
                    "latitude": latitude,
                    "longitude": longitude
                }
            }
        }

    return {"address": texto}


def formatar_duracao(duracao):
    """Converte a duração da API em segundos para horas e minutos."""

    if not duracao:
        return None

    match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(duracao))

    if not match:
        return str(duracao)

    segundos = int(float(match.group(1)))
    horas, resto = divmod(segundos, 3600)
    minutos = round(resto / 60)

    if minutos == 60:
        horas += 1
        minutos = 0

    if horas and minutos:
        return f"{horas} h {minutos} min"
    if horas:
        return f"{horas} h"
    return f"{minutos} min"


def get_google_route(origem, destino, api_key):
    """
    Consulta a Google Routes API.
    Retorna distância em metros, tempo formatado e mensagem de erro.
    """

    try:
        corpo = {
            "origin": montar_ponto(origem),
            "destination": montar_ponto(destino),
            "travelMode": "DRIVE",
            "languageCode": "pt-BR",
            "units": "METRIC"
        }

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK
        }

        response = requests.post(
            URL_ROUTES,
            headers=headers,
            json=corpo,
            timeout=30
        )

        try:
            data = response.json()
        except ValueError:
            return None, None, (
                f"Resposta inválida da API. HTTP {response.status_code}"
            )

        if not response.ok:
            error = data.get("error", {})
            mensagem = error.get("message", response.text[:500])
            codigo = error.get("status", response.status_code)

            return None, None, f"{codigo}: {mensagem}"

        routes = data.get("routes", [])

        if not routes:
            return None, None, "Nenhuma rota encontrada."

        route = routes[0]
        distancia = route.get("distanceMeters")
        duracao = route.get("duration")

        if distancia is None or duracao is None:
            return None, None, "Distância ou duração ausente na resposta."

        tempo = formatar_duracao(duracao)

        return distancia, tempo, None

    except requests.exceptions.Timeout:
        return None, None, "Tempo limite de conexão excedido."

    except requests.exceptions.RequestException as erro:
        return None, None, f"Erro de conexão: {erro}"

    except Exception as erro:
        return None, None, str(erro)


# ============================================================
# INTERFACE STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Automação Matriz OD",
    layout="wide"
)

st.title("🚗 Automação de Matriz Origem-Destino")

st.markdown("""
Envie sua matriz OD em Excel. A aplicação consulta a Google Routes API
para cada chave única e preenche a distância e o tempo na matriz completa.
""")

with st.sidebar:
    st.header("Configurações")

    api_key = st.text_input(
        "Insira sua Google API Key:",
        type="password"
    )

    st.info("A chave não é gravada no arquivo Excel.")

uploaded_file = st.file_uploader(
    "Envie sua matriz Excel (.xlsx)",
    type=["xlsx"]
)


if uploaded_file is not None:

    try:
        df_original = pd.read_excel(uploaded_file)

        # Remove espaços extras dos nomes das colunas.
        df_original.columns = [
            str(col).strip() for col in df_original.columns
        ]

        st.success(
            f"Arquivo carregado com {len(df_original)} linhas."
        )

        obrigatorias = ["chave", "origem", "destino"]

        faltantes = [
            coluna for coluna in obrigatorias
            if coluna not in df_original.columns
        ]

        if faltantes:
            st.error(
                "Colunas obrigatórias ausentes: "
                + ", ".join(faltantes)
            )

        elif not api_key.strip():
            st.warning("Insira sua Google API Key na barra lateral.")

        else:
            # Normaliza as chaves textuais sem alterar sua identidade.
            df_original["chave"] = df_original["chave"].apply(
                lambda x: x.strip() if isinstance(x, str) else x
            )

            chaves_validas = (
                df_original["chave"].notna()
                & df_original["chave"].astype(str).str.strip().ne("")
            )

            df_unicos = (
                df_original.loc[chaves_validas]
                .drop_duplicates(subset=["chave"])
                .copy()
            )

            total_unicos = len(df_unicos)

            st.write(
                f"**{total_unicos}** chaves únicas válidas para consulta."
            )

            if total_unicos == 0:
                st.warning("Não há chaves válidas para consultar.")

            elif st.button("Iniciar processamento", type="primary"):

                resultados = {}

                progress_bar = st.progress(0)
                status_text = st.empty()
                erros_area = st.container()

                # Consulta cada chave única apenas uma vez.
                for i, (_, row) in enumerate(df_unicos.iterrows()):

                    chave = row["chave"]
                    origem = row["origem"]
                    destino = row["destino"]

                    status_text.text(
                        f"Consultando {i + 1}/{total_unicos}: "
                        f"{origem} → {destino}"
                    )

                    distancia, tempo, erro = get_google_route(
                        origem,
                        destino,
                        api_key.strip()
                    )

                    resultados[chave] = {
                        "distancia": distancia,
                        "tempo": tempo,
                        "erro": erro
                    }

                    if erro:
                        with erros_area:
                            st.warning(
                                f"Chave {chave}: "
                                f"{origem} → {destino} | {erro}"
                            )

                    progress_bar.progress((i + 1) / total_unicos)

                    # Pequena pausa entre consultas.
                    time.sleep(0.1)

                status_text.text(
                    "Consultas finalizadas. Preparando o Excel..."
                )

                def obter_resultado(chave, campo):
                    if pd.isna(chave):
                        return None

                    registro = resultados.get(chave)

                    if registro is None:
                        return None

                    return registro[campo]

                # Reaplica os resultados a todas as linhas,
                # inclusive às que possuem chaves repetidas.
                df_original["distancia"] = df_original["chave"].apply(
                    lambda chave: obter_resultado(chave, "distancia")
                )

                df_original["tempo"] = df_original["chave"].apply(
                    lambda chave: obter_resultado(chave, "tempo")
                )

                df_original["erro_consulta"] = df_original["chave"].apply(
                    lambda chave: obter_resultado(chave, "erro")
                )

                sucessos = sum(
                    1 for r in resultados.values()
                    if r["erro"] is None
                )

                falhas = total_unicos - sucessos

                st.subheader("Resultado final")

                c1, c2, c3 = st.columns(3)
                c1.metric("Linhas da matriz", len(df_original))
                c2.metric("Consultas concluídas", sucessos)
                c3.metric("Consultas com erro", falhas)

                st.dataframe(
                    df_original.head(20),
                    use_container_width=True
                )

                # Gera o arquivo Excel para download.
                output = io.BytesIO()

                with pd.ExcelWriter(
                    output,
                    engine="xlsxwriter"
                ) as writer:
                    df_original.to_excel(
                        writer,
                        index=False,
                        sheet_name="Matriz_Processada"
                    )

                st.download_button(
                    label="📥 Baixar matriz completa preenchida",
                    data=output.getvalue(),
                    file_name="matriz_finalizada.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    )
                )

                if falhas:
                    st.warning(
                        f"{falhas} consultas falharam. "
                        "Confira a coluna erro_consulta no Excel."
                    )
                else:
                    st.success("Todas as consultas foram concluídas.")

    except Exception as erro:
        st.error(f"Não foi possível processar o arquivo: {erro}")
