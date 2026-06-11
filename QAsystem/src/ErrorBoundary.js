import React from 'react';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error('[ErrorBoundary] 捕获到组件异常:', error, errorInfo);
    }

    handleRetry = () => {
        this.setState({ hasError: false, error: null });
    };

    render() {
        if (this.state.hasError) {
            return (
                <div className="error-boundary-fallback">
                    <div className="error-boundary-icon">&#9888;</div>
                    <p>{this.props.message || '该模块加载失败，请查看文本信息'}</p>
                    <button onClick={this.handleRetry}>
                        重试
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;
