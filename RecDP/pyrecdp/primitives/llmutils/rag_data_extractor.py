import argparse
from typing import Optional, List

from pyrecdp.core.utils import Timer
from pyrecdp.primitives.operations.logging_utils import logger

from pyrecdp.LLM import TextPipeline
from pyrecdp.primitives.operations import UrlLoader, DocumentSplit, DocumentIngestion, RAGTextFix, DirectoryLoader


def rag_data_prepare(
        files_path: str = None,
        target_urls: List[str] = None,
        text_splitter: str = "RecursiveCharacterTextSplitter",
        text_splitter_args: Optional[dict] = None,
        vs_output_dir: str = "recdp_vs",
        vector_store_type: str = 'FAISS',
        index_name: str = 'recdp_index',
        embeddings_type: str = 'HuggingFaceEmbeddings',
        embeddings_args: Optional[dict] = None,
):
    if bool(files_path):
        loader = DirectoryLoader(files_path, glob="**/*.pdf")
    elif bool(target_urls):
        loader = UrlLoader(urls=target_urls, target_tag='div')
    else:
        logger.error("You must specify at least one parameter in files_path and target_urls")
        exit(1)
    if text_splitter_args is None:
        text_splitter_args = {"chunk_size": 500, "chunk_overlap": 0}
    if embeddings_args is None:
        embeddings_args = {'model_name': f"sentence-transformers/all-mpnet-base-v2"}
    pipeline = TextPipeline()
    ops = [
        loader,
        RAGTextFix(),
        DocumentSplit(text_splitter=text_splitter, text_splitter_args=text_splitter_args),
        DocumentIngestion(
            vector_store=vector_store_type,
            vector_store_args={
                "output_dir": vs_output_dir,
                "index": index_name
            },
            embeddings=embeddings_type,
            embeddings_args=embeddings_args
        ),
    ]
    pipeline.add_operations(ops)
    pipeline.execute()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    # data_files, dup_dir, ngram_size, num_perm, bands, ranges
    # pipeline = minHashLSH_prepare(df, num_perm = 256, ngram_size = 6, bands = 9, ranges = 13)
    parser.add_argument("--files_path", dest="files_path", type=str)
    parser.add_argument("--target_urls", dest="target_urls", type=str)
    parser.add_argument("--text_splitter", dest="text_splitter", type=str, default='RecursiveCharacterTextSplitter')
    parser.add_argument("--vs_output_dir", dest="vs_output_dir", type=str, default='recdp_vs')
    parser.add_argument("--vector_store_type", dest="vector_store_type", type=str, default='FAISS')
    parser.add_argument("--index_name", dest="index_name", type=str, default='recdp_index')
    parser.add_argument("--embeddings_type", dest="embeddings_type", type=str, default='HuggingFaceEmbeddings')
    args = parser.parse_args()
    files_path = args.files_path
    if args.target_urls:
        target_urls = args.target_urls.split(",")
    else:
        target_urls = []
    text_splitter = args.text_splitter
    vs_output_dir = args.vs_output_dir
    vector_store_type = args.vector_store_type
    index_name = args.index_name
    embeddings_type = args.embeddings_type

    with Timer(f"Process RAG data"):
        rag_data_prepare(files_path=files_path,
                         target_urls=target_urls,
                         text_splitter=text_splitter,
                         vs_output_dir=vs_output_dir,
                         vector_store_type=vector_store_type,
                         index_name=index_name,
                         embeddings_type=embeddings_type,
                         )
