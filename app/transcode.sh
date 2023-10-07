if [ $url -eq "" ] || [ $name -eq "" ]
  then
    echo "No arguments supplied"
fi

while getopts u:n: flag
do
    case "${flag}" in
        u) url=${OPTARG};;
        n) name=${OPTARG};;
    esac
done

rm -r "$name"
mkdir -p "$name"
cd "$name"

ffmpeg -i "$url" \
-filter_complex \
"[0:v]split=2[v1][v2]; \
[v1]scale=-1:720[v1out]; [v2]scale=-2:480[v2out]" \
-map [v1out] -c:v:0 libx264 -crf 28 -tune stillimage -b:v:0 5M -maxrate 5M \
-map [v2out] -c:v:1 libx264 -crf 28 -tune stillimage -b:v:1 2.5M -maxrate 2.5M \
-map a:0 -c:a:0 aac -b:a:0 96k -ac 2 \
-map a:0 -c:a:1 aac -b:a:1 96k -ac 2 \
-f hls \
-hls_time 2 \
-hls_playlist_type vod \
-hls_flags independent_segments \
-hls_segment_type mpegts \
-hls_segment_filename stream_%v/data%02d.ts \
-master_pl_name master.m3u8 \
-var_stream_map "v:0,a:0 v:1,a:1" stream_%v/stream.m3u8