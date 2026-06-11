const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://192.168.100.104:5000',
      changeOrigin: true,
      pathRewrite: (path, req) => `/api${path}`,
    })
  );
};