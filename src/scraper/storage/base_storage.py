from abc import ABC, abstractmethod
print("LOADING BASE_STORAGE FROM:", __file__)
class BaseStorage(ABC):

    @abstractmethod
    def create_products_table(self):
        pass

    @abstractmethod
    def insert_products(self, products_data, category_id):
        pass