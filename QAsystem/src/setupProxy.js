const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:5000',
      changeOrigin: true,
      pathRewrite: (path, req) => `/api${path}`,
      timeout: 300000,
      proxyTimeout: 300000,
    })
  );
};