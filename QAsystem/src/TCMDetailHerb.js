import React from 'react';
import { useParams } from 'react-router-dom';
import './TCMDetail.css';

const herbDetails = {
  '水八角': {
    medicinalValue: `
      中文名：水八角 (《分类草药性》)
      【别名】花鸡公、一口血、枫香细辛(《四川中药志》)，裂叶秋海棠、虎爪龙、水黄连、水蜈蚣、风吹不动(《江西草药》)。
      【植物形态】掌裂叶秋海棠。
      【采集】9～10月采挖。
      【性味】酸，平。
      《分类草药性》记载："味甘，无毒。""治黄肿。"
      《四川中药志》："性平，味酸，无毒。""能散血止血。治肾病黄肿、蛇咬伤及妇女火疳、热疳。"
      《江西草药》："性寒，味酸。""祛风活血，利水消肿。"
      水八角味酸，性平，水八角具有解毒止痛、利湿消肿的作用。水八角又叫做一口血、花鸡公，是秋海棠科植物长裂叶秋海棠的根茎，主要是在9到10月份的时候采挖，去除泥沙和根须，洗干净，切成片晒干，备用入药。水八角具有祛风活血，利水，解毒之功效。可用于外伤出血、胃痛、治风湿关节疼痛、水肿、毒蛇咬伤、跌打损伤、尿血、崩漏等。
    `,
    pharmacologicalValue: `
      水八角内服：煎汤，3～4钱(鲜者1～2两)；或炖肉吃。
      水八角治急性关节炎：裂叶秋海棠根五钱，水酒煎服；若关节痛甚，用裂叶秋海棠鲜根适量，酒糟少许，捣烂外敷。
      水八角治全身浮肿、尿血：裂叶秋梅棠根六钱，乌韭根五钱，车前三钱，水煎服。
      水八角治跌打损伤：裂叶秋海棠根适量，晒干研末，每服二钱，开水送服；另用鲜根适量，甜酒糟少许，捣烂外敷。
      水八角治五步龙、银环蛇咬伤：裂叶秋海棠根一两，大青叶五钱，万年青叶三片(均鲜)，水煎服；药渣捣烂外敷。(选方均出《江西草药》)
    `
  }
};

const TCMDetailHerb = () => {
  const { name } = useParams();
  const details = herbDetails[name] || {};

  return (
    <div className="tcm-detail-container">
      <h1>{name}</h1>
      <p><strong>药用价值：</strong>{details.medicinalValue}</p>
      <p><strong>药理价值：</strong>{details.pharmacologicalValue}</p>
    </div>
  );
};

export default TCMDetailHerb;
