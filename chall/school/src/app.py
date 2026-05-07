from flask import Flask, request
from jinja2 import Template

app = Flask(__name__)

# Blog posts database
BLOG_POSTS = {
    '1': {
        'title': 'Welcome to Our New Blog',
        'author': 'Principal Smith',
        'date': 'January 9, 2026',
        'content': 'Welcome to Greenfield High School\'s official blog! Here we share updates, student achievements, and school news.'
    },
    '2': {
        'title': 'Basketball Season Begins',
        'author': 'Coach Johnson',
        'date': 'January 8, 2026',
        'content': 'Our basketball team is ready for an amazing season. Go Wildcats!'
    },
    '3': {
        'title': 'Science Fair Results',
        'author': 'Ms. Brown',
        'date': 'January 7, 2026',
        'content': 'Congratulations to all students who participated in our annual science fair!'
    },
    '4': {
        'title': 'Student Awards Announced',
        'author': 'Admin',
        'date': 'January 6, 2026',
        'content': 'We are proud to announce this month\'s student of the month winners.'
    }
}

def load_template():
    try:
        with open('templates/index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return "<html><body>Error loading template</body></html>"

@app.route("/")
def home():
    template_src = load_template()

    blog_content = """
    <div class="max-w-4xl mx-auto text-center py-12">
      <h2 class="text-4xl font-bold mb-6">Welcome to Greenfield High School Blog</h2>
      <p class="text-lg text-gray-600 mb-8">Stay updated with the latest news, events, and achievements from our school community.</p>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
        <div class="bg-white rounded-lg shadow-md p-6">
          <h3 class="text-2xl font-bold text-blue-600 mb-3">📰 Latest News</h3>
          <p class="text-gray-700 mb-4">Read the latest updates from our school.</p>
          <a href="/blog" class="text-blue-600 hover:underline font-semibold">View All Posts →</a>
        </div>

        <div class="bg-white rounded-lg shadow-md p-6">
          <h3 class="text-2xl font-bold text-blue-600 mb-3">🎓 About Us</h3>
          <p class="text-gray-700 mb-4">Learn more about Greenfield High School.</p>
          <a href="/about" class="text-blue-600 hover:underline font-semibold">Learn More →</a>
        </div>

        <div class="bg-white rounded-lg shadow-md p-6">
          <h3 class="text-2xl font-bold text-blue-600 mb-3">⭐ Recent Highlights</h3>
          <p class="text-gray-700 mb-4">Celebrating student achievements.</p>
          <a href="/blog" class="text-blue-600 hover:underline font-semibold">Explore →</a>
        </div>
      </div>
    </div>
    """

    template_src = template_src.replace('__BLOG_CONTENT__', blog_content)
    t = Template(template_src)
    return t.render()

@app.route("/blog")
def blog():
    template_src = load_template()

    blog_content = '<div class="max-w-4xl mx-auto"><h2 class="text-3xl font-bold mb-8">Recent Posts</h2>'
    blog_content += '<div class="grid gap-6">'
    for post_id, post in BLOG_POSTS.items():
        blog_content += """
        <div class="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition">
          <a href="/blog/""" + post_id + """?note=Great%20post!" class="block">
            <h3 class="text-2xl font-bold text-blue-600 hover:text-blue-700 mb-2">""" + post['title'] + """</h3>
          </a>
          <div class="text-sm text-gray-600 mb-4">
            <span>By """ + post['author'] + """</span> • <span>""" + post['date'] + """</span>
          </div>
          <p class="text-gray-700 mb-4">""" + post['content'][:100] + """...</p>
          <a href="/blog/""" + post_id + """?note=Great%20post!" class="text-blue-600 hover:underline">Read more →</a>
        </div>
        """
    blog_content += '</div></div>'

    template_src = template_src.replace('__BLOG_CONTENT__', blog_content)
    t = Template(template_src)
    return t.render()

@app.route("/blog/<post_id>")
def post_detail(post_id):
    template_src = load_template()

    note = request.args.get('note', 'No additional notes')

    if post_id in BLOG_POSTS:
        post = BLOG_POSTS[post_id]
        blog_content = """
        <div class="max-w-2xl mx-auto">
          <a href="/blog" class="text-blue-600 hover:underline mb-6 inline-block">← Back to all posts</a>
          <article class="bg-white rounded-lg shadow-md p-8">
            <h1 class="text-4xl font-bold mb-2">""" + post['title'] + """</h1>
            <div class="flex gap-4 text-sm text-gray-600 mb-6 pb-6 border-b">
              <span>By """ + post['author'] + """</span>
              <span>""" + post['date'] + """</span>
            </div>
            <div class="prose prose-sm max-w-none text-gray-700 leading-relaxed mb-8">
              """ + post['content'] + """
            </div>
            <hr class="my-8">
            <div class="bg-blue-50 p-4 rounded border-l-4 border-blue-600">
              <h3 class="font-bold text-blue-700 mb-2">📝 Custom Note:</h3>
              <p class="text-gray-700">{{ note }}</p>
            </div>
          </article>
        </div>
        """
        # SSTI vulnerability
        blog_content = blog_content.replace('{{ note }}', note)
    else:
        blog_content = '<div class="text-center text-gray-600"><p>Post not found</p></div>'

    template_src = template_src.replace('__BLOG_CONTENT__', blog_content)
    t = Template(template_src)
    return t.render(o=open)

@app.route("/about")
def about():
    template_src = load_template()

    blog_content = """
    <div class="max-w-4xl mx-auto">
      <h2 class="text-4xl font-bold mb-8">About Greenfield High School</h2>

      <div class="bg-white rounded-lg shadow-md p-8 mb-8">
        <h3 class="text-2xl font-bold text-blue-600 mb-4">Our Mission</h3>
        <p class="text-gray-700 leading-relaxed mb-4">
          Greenfield High School is committed to providing an excellent education that prepares students for success in college,
          career, and life. We foster a supportive community where every student can achieve their full potential.
        </p>
      </div>

      <div class="bg-white rounded-lg shadow-md p-8 mb-8">
        <h3 class="text-2xl font-bold text-blue-600 mb-4">Our Vision</h3>
        <p class="text-gray-700 leading-relaxed mb-4">
          To inspire and empower students to become responsible, innovative, and compassionate leaders in a rapidly changing world.
        </p>
      </div>

      <div class="bg-white rounded-lg shadow-md p-8">
        <h3 class="text-2xl font-bold text-blue-600 mb-4">Why Choose Greenfield?</h3>
        <ul class="text-gray-700 leading-relaxed space-y-2">
          <li>✓ Dedicated and experienced faculty</li>
          <li>✓ State-of-the-art facilities</li>
          <li>✓ Comprehensive academic programs</li>
          <li>✓ Rich extracurricular activities</li>
          <li>✓ Strong community partnerships</li>
        </ul>
      </div>
    </div>
    """

    template_src = template_src.replace('__BLOG_CONTENT__', blog_content)
    t = Template(template_src)
    return t.render()

if __name__ == "__main__":
    app.run()
