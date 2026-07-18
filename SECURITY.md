# Política de segurança

## Como reportar uma vulnerabilidade

Não abra uma issue pública com detalhes exploráveis, chaves ou dados pessoais. Use o recurso
**Security → Report a vulnerability** do repositório no GitHub para enviar um relato privado.
Inclua impacto, passos mínimos de reprodução e, se possível, uma sugestão de correção.

O mantenedor fará a triagem e responderá pelo próprio canal privado. Depois da correção, a
divulgação coordenada poderá registrar impacto e versões afetadas sem expor usuários.

## Escopo prioritário

- vazamento de chaves do OpenRouter ou do cofre local;
- SSRF, redirecionamento para rede privada e downloads sem limite;
- path traversal ou escape por symlink;
- execução de comandos não permitidos pela bridge Electron;
- XSS, quebra da CSP, sandbox ou `contextIsolation`;
- dependência comprometida ou vulnerável.

## Boas práticas para quem usa

- Guarde chaves somente no `.env` ignorado ou no cofre `.audiofy/keys.json`.
- Revogue imediatamente qualquer chave exposta e não a reutilize.
- Revise conteúdo e áudio gerados antes de publicar.
- Mantenha dependências atualizadas após a CI e as auditorias passarem.
