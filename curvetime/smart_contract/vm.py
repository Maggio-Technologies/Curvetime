class SimpleVM:
    def execute(self, code: str, context: dict):
        # 占位，使用eval极不安全，仅演示
        return eval(code, context)