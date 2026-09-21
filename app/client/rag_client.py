import logging
from typing import Dict, Any, List, Tuple
import httpx
from app.config import settings

logger = logging.getLogger("ragear.client")

class RAGClient:
    def __init__(self, base_url: str = None, timeout: float = None):
        self.base_url = (base_url or settings.rag_server_url).rstrip("/")
        self.timeout = timeout or settings.rag_timeout

    async def ask(self, query: str, k_ric: int = 50, llm_help: bool = False) -> Dict[str, Any]:
        """
        Query the central UNINETTUNO RAG server's /ask endpoint.
        Uses LLMHelp=false by default for maximum speed and pure semantic ranking.
        """
        url = f"{self.base_url}/ask"
        params = {
            "query": query,
            "k_ric": k_ric,
            "LLMHelp": "true" if llm_help else "false"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    logger.error(f"RAG server error {response.status_code}: {response.text}")
                    raise RuntimeError(f"RAG Server returned status {response.status_code}: {response.text}")
                
                data = response.json()
                return data
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to RAG server at {self.base_url}: {e}")
            raise ConnectionError(f"Impossibile connettersi al server RAG su {self.base_url}. Verifica che il server sia attivo.") from e
        except httpx.TimeoutException as e:
            logger.error(f"Timeout connecting to RAG server at {self.base_url}: {e}")
            raise TimeoutError(f"Il server RAG su {self.base_url} non ha risposto entro {self.timeout}s.") from e
        except Exception as e:
            logger.error(f"Unexpected error in RAG client: {e}")
            raise

    async def list_all(self) -> List[Dict[str, Any]]:
        """
        Fetch all indexed chunks from the RAG server for dynamic catalog synchronization.
        """
        url = f"{self.base_url}/list"
        try:
            # Listing all chunks may take slightly longer, set a reasonable timeout
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("chunks", [])
                else:
                    logger.warning(f"Failed to list all chunks from {url}: status {response.status_code}")
                    return []
        except Exception as e:
            logger.warning(f"Could not sync with RAG /list ({e}). Will use local catalog cache.")
            return []

    async def check_health(self) -> Tuple[bool, str]:
        """
        Check if the RAG server is reachable.
        """
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(f"{self.base_url}/")
                if resp.status_code == 200:
                    return True, "Server RAG Online e operativo"
                return False, f"Server RAG ha risposto con codice {resp.status_code}"
        except httpx.ConnectError:
            return False, f"Server RAG non raggiungibile ({self.base_url})"
        except httpx.TimeoutException:
            return False, f"Timeout connessione verso {self.base_url}"
        except Exception as e:
            return False, f"Errore connessione: {str(e)}"

rag_client = RAGClient()
