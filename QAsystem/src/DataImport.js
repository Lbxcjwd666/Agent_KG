import React, { useContext, useEffect } from 'react';
import { DataContext } from './DataContext';

const DataImport = () => {
  const { setData } = useContext(DataContext);

  useEffect(() => {
    fetch('/data.json')
      .then(response => response.json())
      .then(jsonData => {
        const filteredData = jsonData.filter(item =>
          ['MED', 'PRE', 'LIT', 'ACU'].includes(item.Label)
        ).map(item => ({
          name: item['Entity Text'],
          type: item.Label === 'MED' ? 'herbs' : item.Label === 'PRE' ? 'formulas' : item.Label === 'LIT' ? 'books' : 'acupuncture',
          id: item.ID
        }));
        console.log('Filtered Data:', filteredData); // 调试输出
        setData(filteredData);
      })
      .catch(error => {
        console.error('Error fetching JSON file:', error);
      });
  }, [setData]);

  return (
    <div>
      <h2>数据已导入</h2>
    </div>
  );
};

export default DataImport;
