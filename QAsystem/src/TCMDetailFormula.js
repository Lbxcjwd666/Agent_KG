import React from 'react';
import { useParams } from 'react-router-dom';
import './TCMDetail.css';

const formulaDetails = {
  '一上散': {
    comp:"雄黄、黑狗脊、蛇床子、硫黄、寒水石、斑蝥",
    prescription: '雄黄（通明，手呵破者）黑狗脊 蛇床子（炒）熟硫黄各15克 寒水石18克 斑蝥13个（去翅、足、毛，研碎）',
    preparation: '上药另研雄黄、硫黄、寒水石如粉，次入斑蝥、蛇床子和黑狗脊为细末，同研匀。',
    indications: '治疥癣。',
    usage: '先洗疥癣，令汤透去痂，油调手中擦热，以鼻中嗅三两次，擦患处，可一上即愈。',
    source: '《兰室秘藏》卷下'
  }
};

const TCMDetailFormula = () => {
  const { name } = useParams();
  const details = formulaDetails[name] || {};

  return (
      <div className="tcm-detail-container">
          <h1>{name}</h1>
          <p><strong>组成：</strong>{details.prescription}</p>
          <p><strong>处方：</strong>{details.prescription}</p>
          <p><strong>制法：</strong>{details.preparation}</p>
          <p><strong>功能主治：</strong>{details.indications}</p>
          <p><strong>用法用量：</strong>{details.usage}</p>
          <p><strong>摘录：</strong>{details.source}</p>
      </div>
  );
};

export default TCMDetailFormula;
