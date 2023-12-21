import os
from typing import Optional
import pip
import importlib
import pathlib
import pkg_resources
from loguru import logger

def singleton(cls):
    instances = {}
    def getinstance():
        if cls not in instances:
            instances[cls] = cls()
        return instances[cls]
    return getinstance

@singleton
class SessionEnvironment:
    def __init__(self):
        self.pip_list=[]
        self.system_list=[]

    def update_pip_list(self, package_or_list):
        def actual_func(package):
            if package not in self.pip_list:
                self.pip_list.append(package)
        if isinstance(package_or_list, list):
            for package in package_or_list:
                actual_func(package)
        elif isinstance(package_or_list, str):
            actual_func(package_or_list)
        else:
            raise ValueError(f"{package_or_list} with type of {type(package_or_list)} is not supported.")

    def get_pip_list(self):
        return self.pip_list

    def update_system_list(self, package_or_list):
        def actual_func(package):
            if package not in self.pip_list:
                self.system_list.append(package)
        if isinstance(package_or_list, list):
            for package in package_or_list:
                actual_func(package)
        elif isinstance(package_or_list, str):
            actual_func(package_or_list)
        else:
            raise ValueError(f"{package_or_list} with type of {type(package_or_list)} is not supported.")

    def get_system_list(self):
        return self.system_list

    def clean(self):
        self.pip_list = []
        self.system_list = []

SessionENV = SessionEnvironment()

def list_requirements(requirements_path):
    with pathlib.Path(requirements_path).open() as requirements_txt:
        install_requires = [
            str(requirement)
            for requirement
            in pkg_resources.parse_requirements(requirements_txt)
        ]
    return install_requires

def fix_package_name(package):
    a = package.split('>')[0]
    a = a.split('<')[0]
    b = a.split('=')[0]
    
    package_name_map = {
        'scikit-learn' : 'sklearn',
        'pyyaml' : 'yaml',
        'Faker' : 'faker',
        'python-docx': 'docx',
        'Pillow': 'pillow',
        'alt-profanity-check': 'profanity_check',
        'faiss-cpu': 'faiss',
        'faiss-gpu': 'faiss',
        'python-docx': 'docx',
        'openai-whisper': 'whisper',
    }
    
    if b in package_name_map:
        b = package_name_map[b]
    #print(b)
    return b

def check_availability_and_install(package_or_list, verbose = 0, force = True):
    if package_or_list == "" or package_or_list == []:
        return
    SessionENV.update_pip_list(package_or_list)
    if verbose == 1:
        logger.info(f"SessionENV pip list is {SessionENV.get_pip_list()}")
    if force:
        local_pip_install(SessionENV.get_pip_list())

def system_install(package_or_list, verbose = 1, force = True):
    if package_or_list == "" or package_or_list == []:
        return
    SessionENV.update_system_list(package_or_list)
    if verbose == 1:
        logger.info(f"SessionENV pip list is {SessionENV.get_system_list()}")
    if force:
        local_system_install(SessionENV.get_system_list())

def local_pip_install(package_or_list):
    logger.info(f"local_pip_install for {package_or_list}")
    for package in package_or_list:
        try:                
            pip_name = fix_package_name(package)
            importlib.import_module(pip_name)
        except:
            pip.main(['install', '-q', package])

def local_system_install(package_or_list):
    logger.info(f"local_system_install for {package_or_list}")
    for package in package_or_list:
        os.system(f"apt install -y {package}")


def import_faiss(no_avx2: Optional[bool] = None, install_if_miss: bool = True):
    """
    Import faiss if available, otherwise raise error.
    If FAISS_NO_AVX2 environment variable is set, it will be considered
    to load FAISS with no AVX2 optimization.

    Args:
        no_avx2: Load FAISS strictly with no AVX2 optimization
            so that the vectorstore is portable and compatible with other devices.
    """
    if no_avx2 is None and "FAISS_NO_AVX2" in os.environ:
        no_avx2 = bool(os.getenv("FAISS_NO_AVX2"))

    try:
        if no_avx2:
            from faiss import swigfaiss as faiss
        else:
            import faiss
    except ImportError:
        if install_if_miss:
            os.system("pip install -q faiss-gpu")
            os.system("pip install -q faiss-cpu")
        else:
            raise ImportError(f"faiss package not found, "
                              f"please install it with 'pip install faiss-gpu && pip install faiss-cpu'")


def import_langchain(install_if_missing: bool = True):
    """
    Import langchain if available, otherwise raise error.
    """
    try:
        from langchain.document_loaders.base import BaseLoader
    except ImportError:
        if install_if_missing:
            os.system("pip install -q langchain")
        else:
            raise ImportError(f"langchain package not found, please install it with 'pip install langchain")


def import_sentence_transformers(install_if_missing: bool = True):
    """
    Import sentence_transformers if available, otherwise raise error.
    """
    try:
        import sentence_transformers

    except ImportError as exc:
        if install_if_missing:
            os.system("pip install -q sentence_transformers")
        else:
            raise ImportError(
                "Could not import sentence_transformers python package. "
                "Please install it with `pip install sentence-transformers`."
            ) from exc


def import_unstructured(install_if_missing: bool = True):
    try:
        import unstructured  # noqa:F401
        from unstructured.partition.auto import partition
    except ImportError:
        if install_if_missing:
            os.system("pip install -q  unstructured")
            os.system("pip install -q  unstructured[ppt, pptx, xlsx]")
        else:
            raise ValueError(
                "unstructured package not found, please install it with "
                "`pip install unstructured`"
            )


def import_openai(install_if_missing: bool = True):
    try:
        import openai
    except ImportError:
        if install_if_missing:
            os.system("pip install -q openai")
        else:
            raise ValueError(
                "openai package not found, please install it with "
                "`pip install openai`"
            )

def import_pysbd(install_if_missing: bool = True):
    try:
        import openai
    except ImportError:
        if install_if_missing:
            os.system("pip install -q pysbd")
        else:
            raise ValueError(
                "pysbd package not found, please install it with "
                "`pip install pysbd`"
            )


