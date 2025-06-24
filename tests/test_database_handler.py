import os
from omerofrontend.database import SqliteDatabaseHandler
import omerofrontend.conf
from omerofrontend.logger import logging

class TestDatabaseHandler:

    @classmethod
    def setup_class(cls):
        cls.sqdbh = SqliteDatabaseHandler()
        logging.getLogger().info(f"Starting {cls.__name__}")
        
    @classmethod
    def teardown_class(cls):
        logging.getLogger().info(f"Stopping {cls.__name__}")
        
        
    def test_initialize_database(self):
        try:
            os.remove(self.sqdbh.DB_FILE)  # Clean up before test
        except FileNotFoundError:
            pass
        self.sqdbh.initialize_database()
        assert self.sqdbh.DB_FILE == f"{omerofrontend.conf.DB_DIR}/{omerofrontend.conf.DB_NAME}"
        assert omerofrontend.conf.DB_DIR is not None
        assert omerofrontend.conf.DB_NAME is not None
        
    def test_insert_import_data(self):
        import_time = "2023-10-01 12:00:00"
        username = "testuser"
        groupname = "testgroup"
        scope = "testscope"
        file_count = 5
        total_file_size_mb = 10.5
        import_time_s = 2.5
        
        self.sqdbh.insert_import_data(import_time, username, groupname, scope, file_count, total_file_size_mb, import_time_s)
        
        # Verify that the data was inserted correctly
        imports = self.sqdbh.get_all_imports()
        assert len(imports) > 0
        assert imports[0][2] == username
        assert imports[0][3] == groupname
        assert imports[0][4] == scope
        assert imports[0][5] == file_count
        assert imports[0][6] == total_file_size_mb
        assert imports[0][7] == import_time_s
        
    # def test_get_all_imports(self):
    #     imports = self.sqdbh.get_all_imports()
    #     assert isinstance(imports, list)
    #     for imp in imports:
    #         assert isinstance(imp, dict)
    #         assert 'time' in imp
    #         assert 'username' in imp
    #         assert 'groupname' in imp
    #         assert 'scope' in imp
    #         assert 'file_count' in imp
    #         assert 'total_file_size_mb' in imp
    #         assert 'import_time_s' in imp