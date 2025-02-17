import string
import nltk

class Tokenizer:
    """
    Base tokenizer class
    """

    def __init__(self, lowercase: bool = True, stopwords: set[str] = None) -> None:
        """
        Make tokenizer
        """
        self.lowercase = lowercase
        self.stopwords = stopwords if stopwords is not None else set()

    def process_token(self, token):
        """
        DESC: Process a token by stripping punctuation and applying lowercasing

        PARAM: token: The token to process

        RETURN: The processed token
        """
        token = token.strip(string.punctuation)
        if self.lowercase:
            token = token.lower()
        return token


class RegexTokenizer(Tokenizer):
    """
    tokenizer that uses a regular expression for tokenization
    """

    def __init__(self, token_regex: str = r'\w+', lowercase: bool = True, stopwords: set[str] = None):
        """
        Make tokenizer with a regular expression
        """
        super().__init__(lowercase, stopwords)
        self.tokenizer = nltk.tokenize.RegexpTokenizer(token_regex)

    def remove_stopwords(self, tokens: list[str], stopwords: set[str]) -> list[str]:
        """
        DESC: remove stopwords from the list of tokens

        PARAM: tokens: list of tokens
               stopwords: set of stopwords

        RETURN: list of tokens without stopwords
        """
        return [token for token in tokens if token not in stopwords]

    def tokenize(self, text: str) -> list[str]:
        """
        DESC: tokenize the text using regex

        PARAM: text: text

        RETURN: tokens
        """
        tokens = self.tokenizer.tokenize(text)
        tokens = [token for token in tokens if token not in self.stopwords]
        return [self.process_token(token) for token in tokens]
    

