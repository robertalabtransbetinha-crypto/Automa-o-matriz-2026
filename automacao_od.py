import streamlit as st
import pandas as pd
import requests
import time
import io

def get_google_distance_matrix(origins, destinations, api_key):
    """
    Consulta a API do Google Maps Distance Matrix.
    """
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origins,
        "destinations": destinations,
        "key": api_key,
        "mode": "driving",
        "language": "pt-BR"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data['status'] == 'OK':
            element = data['rows'][0]['elements'][0]
            if element['status'] == 'OK':
                dist_val = element['distance']['value'] # em metros
                duration_txt = element['duration']['text'] # ex: "5 hours 28 mins"
                return dist_val, duration_txt
            else:
                return None, f"Erro no elemento: {element['status']}"
        else:
            return None, f"Erro na API: {data['status']}"
    except Exception as e:
        return None, str(e)

st.set_page_config(page_title="Automação Matriz OD", layout="wide")

st.title("🚗 Automação de Matriz Origem-Destino")
st.markdown("""
Esta ferramenta processa sua matriz OD, consulta a API do Google Maps apenas para chaves únicas 
e preenche automaticamente toda a planilha original.
""")

# Sidebar para configurações
with st.sidebar:
    st.header("Configurações")
    api_key = st.text_input("Insira sua Google API Key:", type="password")
    st.info("Sua chave não será armazenada.")

# Upload do arquivo
uploaded_file = st.file_uploader("Arraste seu arquivo Excel aqui (.xlsx)", type=["xlsx"])

if uploaded_file and api_key:
    # Ler a matriz
    df_original = pd.read_excel(uploaded_file)
    
    st.success(f"Arquivo carregado com {len(df_original)} linhas.")
    
    # Identificar chaves únicas
    if 'chave' in df_original.columns:
        df_unicos = df_original.drop_duplicates(subset=['chave']).copy()
        total_unicos = len(df_unicos)
        st.write(f"Encontradas **{total_unicos}** chaves únicas para consulta.")
        
        if st.button("Iniciar Processamento"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Dicionário para armazenar resultados {chave: (distancia, tempo)}
            resultados = {}
            
            # Loop de consulta
            for i, (idx, row) in enumerate(df_unicos.iterrows()):
                chave = row['chave']
                origem = row['origem']
                destino = row['destino']
                
                status_text.text(f"Consultando ({i+1}/{total_unicos}): {origem} ➔ {destino}")
                
                dist, tempo = get_google_distance_matrix(origem, destino, api_key)
                
                if dist is not None:
                    resultados[chave] = (dist, tempo)
                else:
                    st.warning(f"Falha na chave: {chave} | Erro: {tempo}")
                
                # Atualizar progresso
                progress_bar.progress((i + 1) / total_unicos)
                
                # Pequeno delay para não sobrecarregar (opcional dependendo da cota)
                # time.sleep(0.1)
            
            status_text.text("✅ Consultas finalizadas! Atualizando matriz completa...")
            
            # Preencher a matriz original
            def map_dist(chave):
                return resultados.get(chave, (None, None))[0]
            
            def map_tempo(chave):
                return resultados.get(chave, (None, None))[1]
            
            df_original['distancia'] = df_original['chave'].apply(map_dist)
            df_original['tempo'] = df_original['chave'].apply(map_tempo)
            
            st.write("### Resultado Final")
            st.dataframe(df_original.head(20))
            
            # Preparar download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_original.to_excel(writer, index=False, sheet_name='Matriz_Processada')
            
            st.download_button(
                label="📥 Baixar Matriz Completa Preenchida",
                data=output.getvalue(),
                file_name="matriz_finalizada.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.error("O arquivo deve conter uma coluna chamada 'chave'.")
elif uploaded_file and not api_key:
    st.warning("Por favor, insira sua Google API Key na barra lateral.")
